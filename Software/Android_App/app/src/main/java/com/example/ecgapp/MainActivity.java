package com.example.ecgapp;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.Base64;

import android.Manifest;
import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothSocket;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.app.AlertDialog;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.github.mikephil.charting.charts.LineChart;
import com.github.mikephil.charting.components.XAxis;
import com.github.mikephil.charting.data.Entry;
import com.github.mikephil.charting.data.LineData;
import com.github.mikephil.charting.data.LineDataSet;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import org.json.JSONException;
import org.json.JSONObject;

public class MainActivity extends AppCompatActivity {

    private TcpClientSender tcpSender;
    private final String PYTHON_SERVER_IP = "192.168.219.54";  // 여기 파이썬 서버가 열어준 IP로 변경
    private final int PYTHON_SERVER_PORT = 9999;

    private static final String TAG = "ECG_APP_CLASSIC";
    private static final int REQUEST_ALL_PERMISSIONS = 1;

    private static final String TARGET_DEVICE_NAME = "HC-06";
    private static final UUID SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");

    private TextView statusTextView;
    private TextView connectionBadge;
    private Button scanButton;
    private Button serverButton;
    private Button registerButton;
    private Button loginButton;
    private Button logoutButton;
    private Button dummyDataButton;
    private Button listUsersButton;
    private Button deleteUserButton;
    private EditText userIdEditText;
    private TextView ecgValueTextView;
    private TextView resultTextView;
    private TextView authStatusTextView;
    private LinearLayout progressLayout;
    private TextView progressStepTextView;
    private ProgressBar progressBar;
    private TextView progressStatusTextView;
    private LineChart ecgChart;
    private LineDataSet dataSet;
    private int dataIndex = 0;
    private static final int MAX_DATA_POINTS = 500;
    // ECG 신호 스무딩을 위한 이동 평균 필터
    private final List<Float> smoothingBuffer = new ArrayList<>();
    private static final int SMOOTHING_WINDOW = 5; // 5개 샘플 이동 평균
    private BluetoothAdapter bluetoothAdapter;
    private BluetoothSocket bluetoothSocket;
    private BluetoothDevice targetDevice;
    private ConnectedThread connectedThread;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private boolean isBluetoothConnected = false;
    private boolean isServerConnected = false;
    private String currentSessionId = null;
    private String loggedInUserId = null;
    private Thread dummyDataThread = null;
    private volatile boolean isDummyDataRunning = false;
    private volatile int dummyDataSampleCount = 0;
    private volatile boolean isRegisterMode = false;
    private volatile boolean isLoginMode = false;
    private volatile int requiredSamples = 3000; // 서버에서 받은 값으로 업데이트됨 (기본: 3000개, 약 6초)
    private static final int STABILIZATION_SECONDS = 5; // 심박 안정화 대기 시간
    private volatile boolean isStabilizing = false; // 안정화 중 플래그
    
    // 더미 데이터 자연스러움을 위한 변수들
    private volatile double currentHeartRate = 72.0; // 현재 심박수 (서서히 변동)
    private volatile double baselineDrift = 0.0; // 베이스라인 드리프트
    private volatile double baselineTarget = 0.0; // 베이스라인 목표값
    private volatile int beatCounter = 0; // 비트 카운터
    private volatile double heartRateVelocity = 0.0; // 심박수 변화 속도


    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        statusTextView = findViewById(R.id.statusTextView);
        connectionBadge = findViewById(R.id.connectionBadge);
        scanButton = findViewById(R.id.scanButton);
        serverButton = findViewById(R.id.serverButton);
        registerButton = findViewById(R.id.registerButton);
        loginButton = findViewById(R.id.loginButton);
        logoutButton = findViewById(R.id.logoutButton);
        dummyDataButton = findViewById(R.id.dummyDataButton);
        listUsersButton = findViewById(R.id.listUsersButton);
        deleteUserButton = findViewById(R.id.deleteUserButton);
        userIdEditText = findViewById(R.id.userIdEditText);
        ecgValueTextView = findViewById(R.id.ecgValueTextView);
        resultTextView = findViewById(R.id.resultTextView);
        authStatusTextView = findViewById(R.id.authStatusTextView);
        progressLayout = findViewById(R.id.progressLayout);
        progressStepTextView = findViewById(R.id.progressStepTextView);
        progressBar = findViewById(R.id.progressBar);
        progressStatusTextView = findViewById(R.id.progressStatusTextView);

        // LineChart 객체 초기화
        ecgChart = findViewById(R.id.ecgChart);
        initChart();

        // 초기 연결 상태 배지
        updateConnectionBadge();

        // 버튼 리스너 설정
        scanButton.setOnClickListener(v -> {
            if (checkConnectPermission()) {
                connectToPairedDevice();
            }
        });

        serverButton.setOnClickListener(v -> toggleTcpConnection());
        
        registerButton.setOnClickListener(v -> startRegister());
        loginButton.setOnClickListener(v -> startLogin());
        logoutButton.setOnClickListener(v -> doLogout());
        dummyDataButton.setOnClickListener(v -> toggleDummyData());
        listUsersButton.setOnClickListener(v -> listUsers());
        deleteUserButton.setOnClickListener(v -> deleteUser());

        // 테스트 모드: 서버 버튼 시작부터 활성화
        serverButton.setEnabled(true);
        updateServerButtonState();
        updateAuthButtonState();
        updateUserManagementButtonState();
    }
    
    // ========== 인증 관련 메서드 ==========
    
    private void startRegister() {
        String userId = userIdEditText.getText().toString().trim();
        if (userId.isEmpty()) {
            Toast.makeText(this, "사용자 ID를 입력하세요.", Toast.LENGTH_SHORT).show();
            return;
        }
        
        if (tcpSender == null) {
            Toast.makeText(this, "서버에 먼저 연결하세요.", Toast.LENGTH_SHORT).show();
            return;
        }
        
        // 확인 다이얼로그 표시
        new AlertDialog.Builder(this)
            .setTitle("등록 확인")
            .setMessage("ECG 데이터를 받으시겠습니까?\n\n등록을 위해 ECG 데이터를 측정합니다.\n(5초 안정화 후 6초간 측정)")
            .setPositiveButton("YES", (dialog, which) -> {
                // YES 선택 시 안정화 후 등록 모드 시작
                startStabilizationCountdown("REGISTER", userId);
            })
            .setNegativeButton("NO", (dialog, which) -> {
                // NO 선택 시 취소
                dialog.dismiss();
            })
            .show();
    }
    
    private void startLogin() {
        String userId = userIdEditText.getText().toString().trim();
        
        if (tcpSender == null) {
            Toast.makeText(this, "서버에 먼저 연결하세요.", Toast.LENGTH_SHORT).show();
            return;
        }
        
        // 확인 다이얼로그 표시
        String message = userId.isEmpty() 
            ? "ECG 데이터를 받으시겠습니까?\n\n로그인을 위해 ECG 데이터를 측정합니다. (전체 검색)\n(5초 안정화 후 6초간 측정)"
            : "ECG 데이터를 받으시겠습니까?\n\n로그인을 위해 ECG 데이터를 측정합니다. (사용자: " + userId + ")\n(5초 안정화 후 6초간 측정)";
        
        new AlertDialog.Builder(this)
            .setTitle("로그인 확인")
            .setMessage(message)
            .setPositiveButton("YES", (dialog, which) -> {
                // YES 선택 시 안정화 후 로그인 모드 시작
                startStabilizationCountdown("LOGIN", userId);
            })
            .setNegativeButton("NO", (dialog, which) -> {
                // NO 선택 시 취소
                dialog.dismiss();
            })
            .show();
    }
    
    // 심박 안정화 카운트다운 후 데이터 수집 시작
    private void startStabilizationCountdown(String mode, String userId) {
        isStabilizing = true;
        dummyDataSampleCount = 0; // 카운트 초기화
        
        String modeText = mode.equals("REGISTER") ? "등록" : "로그인";
        
        // 카운트다운 스레드
        new Thread(() -> {
            try {
                for (int i = STABILIZATION_SECONDS; i > 0; i--) {
                    final int remaining = i;
                    handler.post(() -> {
                        showProgress(modeText, "💓 심박 안정화 중... " + remaining + "초", 0, "편안하게 호흡하세요");
                        statusTextView.setText("심박 안정화 중... " + remaining + "초");
                    });
                    Thread.sleep(1000);
                }
                
                // 카운트다운 완료 - 실제 데이터 수집 시작
                handler.post(() -> {
                    isStabilizing = false;
                    
                    if (mode.equals("REGISTER")) {
                        isRegisterMode = true;
                        isLoginMode = false;
                        showProgress("등록", "📊 ECG 데이터 수집 중...", 0, "");
                        tcpSender.sendCommand("REGISTER:" + userId);
                        statusTextView.setText("등록 데이터 수집 중: " + userId);
                    } else {
                        isLoginMode = true;
                        isRegisterMode = false;
                        if (userId.isEmpty()) {
                            showProgress("로그인", "📊 ECG 데이터 수집 중... (전체 검색)", 0, "");
                            tcpSender.sendCommand("LOGIN");
                        } else {
                            showProgress("로그인", "📊 ECG 데이터 수집 중... (사용자: " + userId + ")", 0, "");
                            tcpSender.sendCommand("LOGIN:" + userId);
                        }
                        statusTextView.setText("로그인 데이터 수집 중");
                    }
                    Toast.makeText(MainActivity.this, "📊 데이터 수집을 시작합니다!", Toast.LENGTH_SHORT).show();
                });
                
            } catch (InterruptedException e) {
                handler.post(() -> {
                    isStabilizing = false;
                    hideProgress();
                    statusTextView.setText("안정화 중단됨");
                });
            }
        }).start();
    }
    
    private void doLogout() {
        if (tcpSender == null) {
            Toast.makeText(this, "서버에 먼저 연결하세요.", Toast.LENGTH_SHORT).show();
            return;
        }
        
        if (loggedInUserId == null && currentSessionId == null) {
            Toast.makeText(this, "로그인 상태가 아닙니다.", Toast.LENGTH_SHORT).show();
            return;
        }
        
        // 로그아웃 명령 전송
        tcpSender.sendCommand("LOGOUT");
        
        // 즉시 로컬 상태 업데이트
        currentSessionId = null;
        loggedInUserId = null;
        isRegisterMode = false;
        isLoginMode = false;
        stopDummyData();
        hideProgress();
        
        handler.post(() -> {
            statusTextView.setText("로그아웃 완료");
            Toast.makeText(this, "👋 로그아웃 완료", Toast.LENGTH_SHORT).show();
            resultTextView.setText("로그아웃 완료");
            updateAuthButtonState();
        });
    }
    
    private void updateAuthButtonState() {
        handler.post(() -> {
            boolean serverConnected = isServerConnected;
            boolean loggedIn = loggedInUserId != null;
            
            registerButton.setEnabled(serverConnected && !loggedIn);
            loginButton.setEnabled(serverConnected && !loggedIn);
            logoutButton.setEnabled(serverConnected && loggedIn);
            
            if (loggedIn) {
                authStatusTextView.setText("✅ 로그인: " + loggedInUserId);
                authStatusTextView.setTextColor(0xFF00AA00);
            } else {
                authStatusTextView.setText("⚪ 로그아웃 상태");
                authStatusTextView.setTextColor(0xFF666666);
            }
        });
    }
    
    private void updateUserManagementButtonState() {
        handler.post(() -> {
            boolean serverConnected = isServerConnected;
            listUsersButton.setEnabled(serverConnected);
            deleteUserButton.setEnabled(serverConnected);
        });
    }
    
    private void listUsers() {
        if (tcpSender == null) {
            Toast.makeText(this, "서버에 먼저 연결하세요.", Toast.LENGTH_SHORT).show();
            return;
        }
        
        tcpSender.sendCommand("USERS");
        statusTextView.setText("사용자 목록 요청 중...");
    }
    
    private void deleteUser() {
        if (tcpSender == null) {
            Toast.makeText(this, "서버에 먼저 연결하세요.", Toast.LENGTH_SHORT).show();
            return;
        }
        
        String userId = userIdEditText.getText().toString().trim();
        if (userId.isEmpty()) {
            Toast.makeText(this, "삭제할 사용자 ID를 입력하세요.", Toast.LENGTH_SHORT).show();
            return;
        }
        
        // 확인 다이얼로그 표시
        new AlertDialog.Builder(this)
            .setTitle("사용자 삭제 확인")
            .setMessage("정말로 사용자 '" + userId + "'를 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없습니다.")
            .setPositiveButton("삭제", (dialog, which) -> {
                tcpSender.sendCommand("DELETE:" + userId);
                statusTextView.setText("사용자 삭제 요청 중: " + userId);
                Toast.makeText(this, "🗑️ 사용자 삭제 요청 전송", Toast.LENGTH_SHORT).show();
            })
            .setNegativeButton("취소", (dialog, which) -> {
                dialog.dismiss();
            })
            .show();
    }
    
    private void handleUserListResponse(JSONObject json) {
        try {
            String status = json.optString("status", "");
            String message = json.optString("message", "");
            
            if ("success".equals(status) && json.has("users")) {
                // 사용자 목록 표시
                org.json.JSONArray usersArray = json.optJSONArray("users");
                if (usersArray != null && usersArray.length() > 0) {
                    StringBuilder userList = new StringBuilder("등록된 사용자 목록:\n\n");
                    for (int i = 0; i < usersArray.length(); i++) {
                        String userId = usersArray.getString(i);
                        userList.append("• ").append(userId).append("\n");
                    }
                    
                    handler.post(() -> {
                        resultTextView.setText(userList.toString());
                        statusTextView.setText("사용자 목록 조회 완료 (" + usersArray.length() + "명)");
                        Toast.makeText(this, "👥 사용자 목록 조회 완료", Toast.LENGTH_SHORT).show();
                    });
                } else {
                    handler.post(() -> {
                        resultTextView.setText("등록된 사용자가 없습니다.");
                        statusTextView.setText("사용자 목록 조회 완료 (0명)");
                        Toast.makeText(this, "등록된 사용자가 없습니다.", Toast.LENGTH_SHORT).show();
                    });
                }
            } else {
                handler.post(() -> {
                    resultTextView.setText("사용자 목록 조회 실패: " + message);
                    Toast.makeText(this, "❌ " + message, Toast.LENGTH_SHORT).show();
                });
            }
        } catch (Exception e) {
            Log.e(TAG, "사용자 목록 응답 처리 실패", e);
            handler.post(() -> {
                Toast.makeText(this, "사용자 목록 처리 중 오류 발생", Toast.LENGTH_SHORT).show();
            });
        }
    }
    
    private void handleUserDeleteResponse(JSONObject json) {
        try {
            String status = json.optString("status", "");
            String message = json.optString("message", "");
            
            if ("success".equals(status)) {
                handler.post(() -> {
                    statusTextView.setText("✅ 사용자 삭제 완료");
                    resultTextView.setText("✅ 사용자 삭제 완료\n" + message);
                    Toast.makeText(this, "✅ 사용자 삭제 완료", Toast.LENGTH_LONG).show();
                    userIdEditText.setText(""); // 입력 필드 초기화
                });
            } else {
                handler.post(() -> {
                    statusTextView.setText("❌ 사용자 삭제 실패");
                    resultTextView.setText("❌ 사용자 삭제 실패\n" + message);
                    Toast.makeText(this, "❌ " + message, Toast.LENGTH_LONG).show();
                });
            }
        } catch (Exception e) {
            Log.e(TAG, "사용자 삭제 응답 처리 실패", e);
            handler.post(() -> {
                Toast.makeText(this, "사용자 삭제 처리 중 오류 발생", Toast.LENGTH_SHORT).show();
            });
        }
    }
    
    // ========== 진행 상태 표시 ==========
    
    private void showProgress(String mode, String step, int progress, String status) {
        handler.post(() -> {
            if (progressLayout != null) {
                progressLayout.setVisibility(android.view.View.VISIBLE);
            }
            if (progressStepTextView != null) {
                progressStepTextView.setText(step);
            }
            if (progressBar != null) {
                progressBar.setProgress(progress);
            }
            if (progressStatusTextView != null) {
                progressStatusTextView.setText(status);
            }
        });
    }
    
    private void hideProgress() {
        handler.post(() -> {
            if (progressLayout != null) {
                progressLayout.setVisibility(android.view.View.GONE);
            }
            if (progressBar != null) {
                progressBar.setProgress(0);
            }
        });
    }
    
    // 로그인 성공 팝업 표시
    private void showLoginSuccessDialog(String userId, double similarity) {
        String similarityPercent = String.format("%.1f%%", similarity * 100);
        
        // 유사도에 따른 등급 결정
        String grade;
        String gradeEmoji;
        if (similarity >= 0.95) {
            grade = "매우 높음";
            gradeEmoji = "🌟";
        } else if (similarity >= 0.90) {
            grade = "높음";
            gradeEmoji = "⭐";
        } else if (similarity >= 0.85) {
            grade = "보통";
            gradeEmoji = "✅";
        } else {
            grade = "낮음";
            gradeEmoji = "⚠️";
        }
        
        String message = "👤 사용자: " + userId + "\n\n" +
                        "📊 ECG 일치율: " + similarityPercent + "\n" +
                        gradeEmoji + " 등급: " + grade + "\n\n" +
                        "생체 인증이 완료되었습니다.";
        
        new android.app.AlertDialog.Builder(this)
            .setTitle("🔓 로그인 성공")
            .setMessage(message)
            .setPositiveButton("확인", (dialog, which) -> dialog.dismiss())
            .setIcon(android.R.drawable.ic_dialog_info)
            .show();
    }
    
    // 로그인 실패 팝업 표시
    private void showLoginFailedDialog(String failType, double similarity, double threshold, String errorMessage) {
        String title;
        String message;
        
        if ("auth_failed".equals(failType)) {
            // 인증 실패 (유사도 부족)
            String similarityPercent = String.format("%.1f%%", similarity * 100);
            String thresholdPercent = String.format("%.1f%%", threshold * 100);
            
            title = "🔒 로그인 실패";
            message = "❌ ECG 인증에 실패했습니다.\n\n" +
                     "📊 측정된 일치율: " + similarityPercent + "\n" +
                     "🎯 필요한 일치율: " + thresholdPercent + " 이상\n\n" +
                     "⚠️ 원인:\n" +
                     "• 등록된 ECG 패턴과 다름\n" +
                     "• 전극 접촉 불량\n" +
                     "• 측정 환경 변화\n\n" +
                     "💡 전극을 확인하고 다시 시도해주세요.";
        } else {
            // 기타 에러 (R-peak 부족 등)
            title = "⚠️ 로그인 실패";
            
            String reason;
            if (errorMessage.contains("R-peak") || errorMessage.contains("insufficient_peaks")) {
                reason = "• ECG 신호에서 심박을 감지하지 못함\n" +
                        "• 전극 접촉 상태를 확인하세요\n" +
                        "• 새 전극 패드 사용을 권장합니다";
            } else if (errorMessage.contains("데이터가 부족")) {
                reason = "• 충분한 ECG 데이터가 수집되지 않음\n" +
                        "• 측정 중 연결이 끊어졌을 수 있음";
            } else if (errorMessage.contains("품질")) {
                reason = "• ECG 신호 품질이 낮음\n" +
                        "• 전극 접촉을 개선해주세요";
            } else {
                reason = "• " + errorMessage;
            }
            
            message = "❌ ECG 처리 중 오류가 발생했습니다.\n\n" +
                     "📋 오류 내용:\n" + reason + "\n\n" +
                     "💡 전극 상태를 확인하고 다시 시도해주세요.";
        }
        
        new android.app.AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(message)
            .setPositiveButton("확인", (dialog, which) -> dialog.dismiss())
            .setIcon(android.R.drawable.ic_dialog_alert)
            .show();
    }
    
    private void updateProgress(int progress, String status) {
        handler.post(() -> {
            if (progressBar != null) {
                progressBar.setProgress(progress);
            }
            if (progressStatusTextView != null) {
                progressStatusTextView.setText(status);
            }
        });
    }
    
    private void setServerConnected(boolean connected) {
        isServerConnected = connected;
        updateAuthButtonState();
        updateUserManagementButtonState();
        updateConnectionBadge();
    }
    
    private void updateConnectionBadge() {
        handler.post(() -> {
            if (connectionBadge == null) return;
            
            if (isServerConnected && isBluetoothConnected) {
                connectionBadge.setText("● 모두 연결됨");
                connectionBadge.setBackgroundResource(R.drawable.status_badge_connected);
            } else if (isServerConnected) {
                connectionBadge.setText("● 서버 연결됨");
                connectionBadge.setBackgroundResource(R.drawable.status_badge_connected);
            } else if (isBluetoothConnected) {
                connectionBadge.setText("● BT 연결됨");
                connectionBadge.setBackgroundResource(R.drawable.status_badge_connected);
            } else {
                connectionBadge.setText("● 연결 안됨");
                connectionBadge.setBackgroundResource(R.drawable.status_badge_disconnected);
            }
        });
    }
    
    private void handleAuthResponse(JSONObject json) {
        try {
            String status = json.optString("status", "");
            String message = json.optString("message", "");
            
            if ("success".equals(status)) {
                // 등록 성공 체크 (우선)
                if (message.contains("등록") || (json.has("user_id") && json.has("registered_at"))) {
                    String userId = json.optString("user_id", "unknown");
                    
                    // 등록 모드 종료 및 더미 데이터 중지
                    isRegisterMode = false;
                    dummyDataSampleCount = 0;
                    stopDummyData();
                    
                    // 등록 완료 배너 표시
                    showProgress("등록", "등록 완료 ✅", 100, message);
                    
                    handler.post(() -> {
                        // "샘플 데이터 수집 완료 - 서버 처리 대기 중..." 메시지 제거
                        statusTextView.setText("✅ 등록 완료: " + userId);
                        Toast.makeText(this, "✅ 샘플 데이터 수집 완료하였습니다. 등록 완료! 이제 로그인하세요.", Toast.LENGTH_LONG).show();
                        resultTextView.setText("✅ 등록 완료\n사용자: " + userId + "\n" + message + "\n\n이제 로그인 버튼을 눌러 로그인하세요.");
                    });
                    
                    // 자동 로그인 제거 (사용자가 직접 로그인하도록)
                    // 등록 후에는 로그아웃 상태 유지
                    currentSessionId = null;
                    loggedInUserId = null;
                    updateAuthButtonState();
                    
                    // 3초 후 진행 상태 숨기기 (완료 메시지는 유지)
                    handler.postDelayed(() -> {
                        hideProgress();
                        handler.post(() -> {
                            statusTextView.setText("✅ 등록 완료: " + userId + " (로그인하세요)");
                        });
                    }, 3000);
                }
                // 로그인 성공
                else if (json.has("session_id") || message.contains("로그인")) {
                    currentSessionId = json.optString("session_id", null);
                    loggedInUserId = json.optString("user_id", "unknown");
                    
                    // 로그인 모드 종료 및 더미 데이터 중지
                    isLoginMode = false;
                    dummyDataSampleCount = 0;
                    stopDummyData();
                    
                    double similarity = json.optDouble("similarity", 0);
                    
                    // 로그인 완료 배너 표시
                    showProgress("로그인", "로그인 완료 ✅", 100, "유사도: " + String.format("%.1f%%", similarity * 100));
                    
                    handler.post(() -> {
                        // "샘플 데이터 수집 완료 - 서버 처리 대기 중..." 메시지 제거
                        statusTextView.setText("✅ 로그인 완료: " + loggedInUserId + " (유사도: " + String.format("%.1f%%", similarity * 100) + ")");
                        resultTextView.setText("✅ 로그인 완료\n사용자: " + loggedInUserId + "\n유사도: " + String.format("%.1f%%", similarity * 100));
                        
                        // 로그인 성공 팝업 표시
                        showLoginSuccessDialog(loggedInUserId, similarity);
                    });
                    
                    updateAuthButtonState();
                    
                    // 3초 후 진행 상태 숨기기 (완료 메시지는 유지)
                    handler.postDelayed(() -> {
                        hideProgress();
                        handler.post(() -> {
                            statusTextView.setText("✅ 로그인: " + loggedInUserId);
                        });
                    }, 3000);
                }
            } 
            else if ("auth_failed".equals(status)) {
                double bestSimilarity = json.optDouble("best_similarity", 0);
                double threshold = json.optDouble("threshold", 0.90);
                
                // 로그인 모드 종료 및 더미 데이터 중지
                isLoginMode = false;
                dummyDataSampleCount = 0;
                stopDummyData();
                
                // 로그인 실패 배너 표시
                showProgress("로그인", "로그인 실패 ❌", 100, "유사도: " + String.format("%.1f%%", bestSimilarity * 100));
                
                handler.post(() -> {
                    statusTextView.setText("❌ 로그인 실패: 인증 실패 (유사도: " + String.format("%.1f%%", bestSimilarity * 100) + ")");
                    resultTextView.setText("❌ 로그인 실패\n인증 실패\n유사도: " + String.format("%.1f%%", bestSimilarity * 100));
                    
                    // 로그인 실패 팝업 표시
                    showLoginFailedDialog("auth_failed", bestSimilarity, threshold, "ECG 패턴이 일치하지 않습니다.");
                });
                
                // 3초 후 진행 상태 숨기기 (실패 메시지는 유지)
                handler.postDelayed(() -> {
                    hideProgress();
                    handler.post(() -> {
                        statusTextView.setText("❌ 로그인 실패");
                    });
                }, 3000);
            }
            // R-peak 부족 (insufficient_peaks)
            else if ("insufficient_peaks".equals(status) || "low_quality".equals(status)) {
                // 로그인/등록 모드 종료
                if (isLoginMode) {
                    isLoginMode = false;
                    dummyDataSampleCount = 0;
                    stopDummyData();
                    
                    showProgress("로그인", "로그인 실패 ❌", 100, "ECG 신호 품질 문제");
                    
                    final String errorMsg = message;
                    handler.post(() -> {
                        statusTextView.setText("❌ 로그인 실패: ECG 신호 품질 문제");
                        resultTextView.setText("❌ 로그인 실패\n" + errorMsg);
                        
                        // 로그인 실패 팝업 표시
                        showLoginFailedDialog("insufficient_peaks", 0, 0.90, errorMsg);
                    });
                    
                    handler.postDelayed(() -> {
                        hideProgress();
                        handler.post(() -> statusTextView.setText("❌ 로그인 실패"));
                    }, 3000);
                } else if (isRegisterMode) {
                    isRegisterMode = false;
                    dummyDataSampleCount = 0;
                    stopDummyData();
                    
                    showProgress("등록", "등록 실패 ❌", 100, "ECG 신호 품질 문제");
                    
                    final String errorMsg = message;
                    handler.post(() -> {
                        statusTextView.setText("❌ 등록 실패: ECG 신호 품질 문제");
                        resultTextView.setText("❌ 등록 실패\n" + errorMsg);
                        
                        // 등록 실패 팝업 표시
                        showLoginFailedDialog("insufficient_peaks", 0, 0.90, errorMsg);
                    });
                    
                    handler.postDelayed(() -> {
                        hideProgress();
                        handler.post(() -> statusTextView.setText("❌ 등록 실패"));
                    }, 3000);
                }
            }
            // 로그아웃
            else if (message.contains("로그아웃") || "success".equals(status) && message.contains("로그아웃")) {
                currentSessionId = null;
                loggedInUserId = null;
                isRegisterMode = false;
                isLoginMode = false;
                stopDummyData();
                hideProgress();
                handler.post(() -> {
                    statusTextView.setText("로그아웃 완료");
                    Toast.makeText(this, "👋 로그아웃 완료", Toast.LENGTH_SHORT).show();
                    resultTextView.setText("로그아웃 완료");
                    updateAuthButtonState();
                });
            }
            // 에러 처리 (등록 실패, 로그인 실패 등)
            else if ("error".equals(status)) {
                // 등록 모드에서 에러 발생
                if (isRegisterMode) {
                    isRegisterMode = false;
                    dummyDataSampleCount = 0;
                    stopDummyData();
                    
                    // 등록 실패 배너 표시
                    showProgress("등록", "등록 실패 ❌", 100, message);
                    
                    handler.post(() -> {
                        statusTextView.setText("❌ 등록 실패: " + message);
                        Toast.makeText(this, "❌ 등록 실패: " + message, Toast.LENGTH_LONG).show();
                        resultTextView.setText("❌ 등록 실패\n" + message);
                    });
                    
                    // 3초 후 진행 상태 숨기기
                    handler.postDelayed(() -> {
                        hideProgress();
                        handler.post(() -> {
                            statusTextView.setText("❌ 등록 실패");
                        });
                    }, 3000);
                }
                // 로그인 모드에서 에러 발생
                else if (isLoginMode) {
                    isLoginMode = false;
                    dummyDataSampleCount = 0;
                    stopDummyData();
                    
                    // 로그인 실패 배너 표시
                    showProgress("로그인", "로그인 실패 ❌", 100, message);
                    
                    final String errorMessage = message;
                    handler.post(() -> {
                        statusTextView.setText("❌ 로그인 실패: " + errorMessage);
                        resultTextView.setText("❌ 로그인 실패\n" + errorMessage);
                        
                        // 로그인 실패 팝업 표시 (에러)
                        showLoginFailedDialog("error", 0, 0.90, errorMessage);
                    });
                    
                    // 3초 후 진행 상태 숨기기
                    handler.postDelayed(() -> {
                        hideProgress();
                        handler.post(() -> {
                            statusTextView.setText("❌ 로그인 실패");
                        });
                    }, 3000);
                }
                // 일반 에러
                else {
                    handler.post(() -> {
                        statusTextView.setText("❌ 오류: " + message);
                        Toast.makeText(this, "❌ " + message, Toast.LENGTH_LONG).show();
                        resultTextView.setText("❌ 오류\n" + message);
                        hideProgress();
                    });
                }
            }
            
        } catch (Exception e) {
            Log.e(TAG, "인증 응답 처리 실패", e);
            // 예외 발생 시에도 진행 상태 정리
            isRegisterMode = false;
            isLoginMode = false;
            stopDummyData();
            hideProgress();
        }
    }
    
    // ========== 더미 데이터 생성 ==========
    
    private void toggleDummyData() {
        if (isDummyDataRunning) {
            stopDummyData();
        } else {
            startDummyData();
        }
    }
    
    private void startDummyData() {
        if (tcpSender == null) {
            Toast.makeText(this, "서버에 먼저 연결하세요.", Toast.LENGTH_SHORT).show();
            return;
        }
        
        if (isDummyDataRunning) {
            return;
        }
        
        isDummyDataRunning = true;
        dummyDataSampleCount = 0;
        dummyDataThread = new Thread(this::generateDummyECGData);
        dummyDataThread.start();
        
        handler.post(() -> {
            dummyDataButton.setText("⏹ 더미 데이터 중지");
            statusTextView.setText("🧪 더미 ECG 데이터 생성 중...");
        });
    }
    
    private void stopDummyData() {
        isDummyDataRunning = false;
        if (dummyDataThread != null) {
            dummyDataThread.interrupt();
            dummyDataThread = null;
        }
        
        handler.post(() -> {
            dummyDataButton.setText("🧪 더미 ECG 데이터 생성 (테스트용)");
            statusTextView.setText("더미 데이터 생성 중지됨");
        });
    }
    
    private void generateDummyECGData() {
        // ECG 파형 시뮬레이션 (심박수 변동, 500Hz 샘플링)
        final int samplingRate = 500; // 500Hz
        
        // 초기화
        currentHeartRate = 72.0 + (Math.random() - 0.5) * 10; // 67-77 BPM 범위
        baselineDrift = 0.0;
        baselineTarget = (Math.random() - 0.5) * 30; // 베이스라인 목표값
        beatCounter = 0;
        heartRateVelocity = (Math.random() - 0.5) * 0.5; // 심박수 변화 속도
        
        int sampleIndex = 0;
        double time = 0;
        double beatStartTime = 0.0;
        double currentBeatDuration = 60.0 / currentHeartRate;
        
        while (isDummyDataRunning && !Thread.currentThread().isInterrupted()) {
            try {
                // 등록/로그인 모드가 아니면 데이터 수집 중지
                if (!isRegisterMode && !isLoginMode) {
                    isDummyDataRunning = false;
                    handler.post(() -> {
                        dummyDataButton.setText("🧪 더미 ECG 데이터 생성 (테스트용)");
                    });
                    break;
                }
                
                // 심박수 변동성 추가 (서서히 변동, 60-85 BPM 범위)
                heartRateVelocity += (Math.random() - 0.5) * 0.1;
                heartRateVelocity = Math.max(-1.0, Math.min(1.0, heartRateVelocity)); // 제한
                currentHeartRate += heartRateVelocity * 0.01;
                currentHeartRate = Math.max(60.0, Math.min(85.0, currentHeartRate)); // 범위 제한
                
                // 베이스라인 드리프트 시뮬레이션
                if (Math.random() < 0.005) { // 가끔 베이스라인 목표 변경
                    baselineTarget = (Math.random() - 0.5) * 30;
                }
                // 베이스라인을 목표값으로 서서히 이동
                baselineDrift += (baselineTarget - baselineDrift) * 0.002;
                
                // 비트 주기 완료 체크 (RR 간격 변동성 포함)
                double timeSinceBeatStart = time - beatStartTime;
                if (timeSinceBeatStart >= currentBeatDuration) {
                    // 다음 비트 시작
                    beatStartTime = time;
                    beatCounter++;
                    
                    // RR 간격 변동성 (부정맥 같은 느낌)
                    double rrVariation = 1.0 + (Math.random() - 0.5) * 0.15; // ±7.5% 변동
                    currentBeatDuration = (60.0 / currentHeartRate) * rrVariation;
                }
                
                // ECG 파형 생성 (P, QRS, T 파 포함)
                int ecgValue = generateECGWaveform(timeSinceBeatStart, currentBeatDuration, beatCounter, time);
                
                // 그래프에 추가
                handler.post(() -> {
                    ecgValueTextView.setText(ecgValue + " mV");
                    addEntry(ecgValue);
                });
                
                // TCP로 전송 (등록/로그인 모드일 때만, 안정화 완료 후)
                if (tcpSender != null && (isRegisterMode || isLoginMode) && !isStabilizing) {
                    tcpSender.sendData(ecgValue);
                    dummyDataSampleCount++;
                    
                    // 진행률 업데이트 (100개마다)
                    if (dummyDataSampleCount % 100 == 0) {
                        int progress = (int) ((dummyDataSampleCount * 100.0) / requiredSamples);
                        progress = Math.min(95, progress); // 최대 95%까지 (수집 중)
                        updateProgress(progress, dummyDataSampleCount + " / " + requiredSamples + " 샘플");
                    }
                    
                    // 필요한 샘플 수를 모두 수집했으면
                    if (dummyDataSampleCount >= requiredSamples) {
                        // 샘플 수집 완료 표시
                        handler.post(() -> {
                            if (isRegisterMode) {
                                showProgress("등록", "샘플 데이터 수집 완료 - 서버 처리 대기 중...", 100, requiredSamples + " / " + requiredSamples + " 샘플");
                                statusTextView.setText("샘플 데이터 수집 완료 - 서버에서 등록 처리 중...");
                                Toast.makeText(MainActivity.this, "📊 샘플 데이터 수집 완료하였습니다. 서버 처리 중...", Toast.LENGTH_SHORT).show();
                            } else if (isLoginMode) {
                                showProgress("로그인", "샘플 데이터 수집 완료 - 서버 처리 대기 중...", 100, requiredSamples + " / " + requiredSamples + " 샘플");
                                statusTextView.setText("샘플 데이터 수집 완료 - 서버에서 로그인 처리 중...");
                                Toast.makeText(MainActivity.this, "📊 샘플 데이터 수집 완료하였습니다. 서버 처리 중...", Toast.LENGTH_SHORT).show();
                            }
                        });
                        // 더미 데이터 전송 중지 (서버가 이미 충분한 데이터를 받았을 수 있음)
                        // 서버가 1000개를 받으면 자동으로 처리 시작
                        isDummyDataRunning = false;
                        handler.post(() -> {
                            dummyDataButton.setText("🧪 더미 ECG 데이터 생성 (테스트용)");
                        });
                        break;
                    }
                }
                // 모드가 아니면 서버로 전송하지 않음 (그래프만 표시)
                
                // 500Hz = 2ms 간격
                Thread.sleep(2);
                
                time += 2.0 / 1000.0; // 초 단위
                sampleIndex++;
                
            } catch (InterruptedException e) {
                isDummyDataRunning = false;
                handler.post(() -> {
                    dummyDataButton.setText("🧪 더미 ECG 데이터 생성 (테스트용)");
                });
                break;
            } catch (Exception e) {
                Log.e(TAG, "더미 데이터 생성 오류", e);
                isDummyDataRunning = false;
                handler.post(() -> {
                    dummyDataButton.setText("🧪 더미 ECG 데이터 생성 (테스트용)");
                });
                break;
            }
        }
        
        // 루프 종료 시 버튼 텍스트 업데이트
        isDummyDataRunning = false;
        handler.post(() -> {
            dummyDataButton.setText("🧪 더미 ECG 데이터 생성 (테스트용)");
        });
    }
    
    private int generateECGWaveform(double timeSinceBeatStart, double beatDuration, int beatNumber, double absoluteTime) {
        // 정규화된 시간 (0~1, 한 비트 주기)
        double normalizedTime = timeSinceBeatStart / beatDuration;
        
        // 베이스라인 (드리프트 포함)
        double baseline = 512.0 + baselineDrift;
        
        // 비트마다 진폭 변동성 추가 (약간씩 다른 파형)
        double amplitudeVariation = 1.0 + (Math.random() - 0.5) * 0.1; // ±5% 변동
        
        // P파 (0.0 ~ 0.15) - 진폭 변동성 포함
        double pWave = 0;
        if (normalizedTime >= 0.0 && normalizedTime < 0.15) {
            double pPhase = (normalizedTime - 0.0) / 0.15;
            double pAmplitude = 20 * amplitudeVariation * (0.9 + Math.random() * 0.2); // ±10% 추가 변동
            pWave = pAmplitude * Math.sin(Math.PI * pPhase);
        }
        
        // QRS 복합체 (0.15 ~ 0.25) - 가장 중요한 파형, 약간의 변동
        double qrsWave = 0;
        if (normalizedTime >= 0.15 && normalizedTime < 0.25) {
            double qrsPhase = (normalizedTime - 0.15) / 0.1;
            // QRS 진폭 변동성 (±3%)
            double qrsAmplitudeFactor = 1.0 + (Math.random() - 0.5) * 0.06;
            // Q, R, S 파 시뮬레이션
            if (qrsPhase < 0.2) {
                qrsWave = -30 * qrsAmplitudeFactor * qrsPhase; // Q파
            } else if (qrsPhase < 0.5) {
                qrsWave = (200 * qrsAmplitudeFactor) * (qrsPhase - 0.2) - 6; // R파 (상승)
            } else if (qrsPhase < 0.8) {
                qrsWave = (200 * qrsAmplitudeFactor) * (0.5 - qrsPhase) + 54; // R파 (하강)
            } else {
                qrsWave = -20 * qrsAmplitudeFactor * (qrsPhase - 0.8); // S파
            }
        }
        
        // T파 (0.25 ~ 0.7) - 진폭 변동성 포함
        double tWave = 0;
        if (normalizedTime >= 0.25 && normalizedTime < 0.7) {
            double tPhase = (normalizedTime - 0.25) / 0.45;
            double tAmplitude = 40 * amplitudeVariation * (0.85 + Math.random() * 0.3); // ±15% 변동
            tWave = tAmplitude * Math.sin(Math.PI * tPhase);
        }
        
        // 다양한 노이즈 추가
        // 1. 백색 노이즈 (항상 존재)
        double whiteNoise = (Math.random() - 0.5) * 8;
        
        // 2. 전원 노이즈 시뮬레이션 (60Hz hum) - 절대 시간 기반으로 연속적
        double powerlineNoise = 2.0 * Math.sin(2 * Math.PI * 60.0 * absoluteTime);
        
        // 3. 근육 노이즈 (가끔 발생하는 큰 노이즈)
        double muscleNoise = 0;
        if (Math.random() < 0.02) { // 2% 확률로 큰 노이즈
            muscleNoise = (Math.random() - 0.5) * 25;
        }
        
        // 4. 베이스라인 고주파 노이즈
        double baselineNoise = (Math.random() - 0.5) * 3;
        
        // 최종 노이즈 합성
        double totalNoise = whiteNoise + powerlineNoise * 0.5 + muscleNoise + baselineNoise;
        
        // 최종 값 계산
        double value = baseline + pWave + qrsWave + tWave + totalNoise;
        
        // 0~1023 범위로 클리핑
        return (int) Math.max(0, Math.min(1023, value));
    }

    @Override
    protected void onResume() {
        super.onResume();
        requestPermissionsIfNeeded();
    }

    //그래프 초기화 메서드
    private void initChart() {
        dataSet = new LineDataSet(new ArrayList<Entry>(), "ECG Signal");

        dataSet.setDrawCircles(false);
        dataSet.setDrawValues(false);

        // ECG 라인 색상 - 시안 색상
        dataSet.setColor(0xFF00E5FF);
        dataSet.setLineWidth(2f);
        dataSet.setMode(LineDataSet.Mode.LINEAR);
        
        // 그라데이션 채우기
        dataSet.setDrawFilled(true);
        dataSet.setFillColor(0xFF00E5FF);
        dataSet.setFillAlpha(30);

        LineData lineData = new LineData(dataSet);
        ecgChart.setData(lineData);

        ecgChart.getDescription().setEnabled(false);
        ecgChart.setTouchEnabled(false);
        ecgChart.getLegend().setEnabled(false);

        // 배경 투명
        ecgChart.setBackgroundColor(0x00000000);

        // X축 스타일
        XAxis xAxis = ecgChart.getXAxis();
        xAxis.setPosition(XAxis.XAxisPosition.BOTTOM);
        xAxis.setDrawLabels(false);
        xAxis.setDrawGridLines(true);
        xAxis.setGridColor(0xFF1E3A5F);
        xAxis.setAxisLineColor(0xFF334155);

        // Y축 스타일 - 0~1024 범위 (Arduino ADC 전체 범위)
        ecgChart.getAxisLeft().setAxisMinimum(0f);
        ecgChart.getAxisLeft().setAxisMaximum(1024f);
        ecgChart.getAxisLeft().setDrawGridLines(true);
        ecgChart.getAxisLeft().setGridColor(0xFF1E3A5F);
        ecgChart.getAxisLeft().setAxisLineColor(0xFF334155);
        ecgChart.getAxisLeft().setTextColor(0xFF94A3B8);
        ecgChart.getAxisRight().setEnabled(false);

        ecgChart.invalidate();
    }

    //데이터 추가 및 그래프 갱신 메서드 (스무딩 적용)
    private void addEntry(int value) {
        // 이동 평균 필터로 스무딩 적용 (노이즈 제거)
        smoothingBuffer.add((float) value);
        if (smoothingBuffer.size() > SMOOTHING_WINDOW) {
            smoothingBuffer.remove(0);
        }
        
        // 이동 평균 계산
        float smoothedValue = value;
        if (smoothingBuffer.size() >= SMOOTHING_WINDOW) {
            float sum = 0;
            for (float v : smoothingBuffer) {
                sum += v;
            }
            smoothedValue = sum / smoothingBuffer.size();
        }
        
        //(X축: dataIndex, Y축: smoothedValue) - 스무딩된 값 사용
        Entry newEntry = new Entry(dataIndex, smoothedValue);
        dataSet.addEntry(newEntry);

        if (dataSet.getEntryCount() > MAX_DATA_POINTS) {
            dataSet.removeFirst();

            for (Entry e : dataSet.getValues()) {
                e.setX(e.getX() - 1);
            }
        }

        ecgChart.getData().notifyDataChanged();
        ecgChart.notifyDataSetChanged();

        ecgChart.setVisibleXRangeMaximum(MAX_DATA_POINTS);
        ecgChart.moveViewToX(dataIndex);

        dataIndex++;
    }

    //권한 요청
    private void requestPermissionsIfNeeded() {
        List<String> perms = new ArrayList<>();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (ActivityCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED)
                perms.add(Manifest.permission.BLUETOOTH_SCAN);
            if (ActivityCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED)
                perms.add(Manifest.permission.BLUETOOTH_CONNECT);
        }
        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED)
            perms.add(Manifest.permission.ACCESS_FINE_LOCATION);

        if (!perms.isEmpty()) {
            ActivityCompat.requestPermissions(this, perms.toArray(new String[0]), REQUEST_ALL_PERMISSIONS);
            return;
        }

        initBluetooth();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode,
                                           @NonNull String[] permissions,
                                           @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_ALL_PERMISSIONS) {
            boolean allGranted = true;
            for (int result : grantResults) if (result != PackageManager.PERMISSION_GRANTED) allGranted = false;

            if (allGranted) {
                Toast.makeText(this, "권한 승인됨", Toast.LENGTH_SHORT).show();
                initBluetooth();
            } else {
                statusTextView.setText("권한 거부됨, 앱 사용 불가");
                scanButton.setEnabled(false);
            }
        }
    }

    //블루투스 초기화
    private void initBluetooth() {
        BluetoothManager manager = (BluetoothManager) getSystemService(Context.BLUETOOTH_SERVICE);
        if (manager == null) {
            statusTextView.setText("블루투스 매니저 오류");
            scanButton.setEnabled(false);
            return;
        }

        bluetoothAdapter = manager.getAdapter();
        if (bluetoothAdapter == null) {
            statusTextView.setText("블루투스 어댑터 오류 (하드웨어 없음)");
            scanButton.setEnabled(false);
            return;
        }

        statusTextView.setText("블루투스 준비 완료. 스캔 버튼 클릭");
        scanButton.setEnabled(true);
    }

    //페어링된 장치 연결
    private void connectToPairedDevice() {
        if (!bluetoothAdapter.isEnabled()) {
            statusTextView.setText("블루투스를 켜주세요");
            return;
        }

        handler.post(() -> {
            statusTextView.setText("페어링된 장치 목록에서 모듈 검색 중...");
            scanButton.setEnabled(false);
        });

        try {
            Set<BluetoothDevice> pairedDevices = bluetoothAdapter.getBondedDevices();
            targetDevice = null;

            Log.d(TAG, "페어링된 장치 개수: " + pairedDevices.size());
            
            // 페어링된 모든 장치 이름 로그 출력
            for (BluetoothDevice device : pairedDevices) {
                String deviceName = device.getName();
                String deviceAddress = device.getAddress();
                Log.d(TAG, "페어링된 장치: 이름=" + deviceName + ", 주소=" + deviceAddress);
                
                if (TARGET_DEVICE_NAME.equals(deviceName)) {
                    targetDevice = device;
                    Log.d(TAG, "타겟 장치 발견: " + deviceName);
                    break;
                }
            }
        } catch (SecurityException e) {
            Log.e(TAG, "페어링된 장치 접근 권한 오류", e);
            handler.post(() -> {
                statusTextView.setText("연결 권한 오류");
                scanButton.setEnabled(true);
            });
            return;
        }

        if (targetDevice != null) {
            Log.d(TAG, "장치 연결 시도: " + targetDevice.getName() + " (" + targetDevice.getAddress() + ")");
            connectToDevice();
        } else {
            Log.w(TAG, "타겟 장치를 찾을 수 없음: " + TARGET_DEVICE_NAME);
            handler.post(() -> {
                statusTextView.setText("❌ " + TARGET_DEVICE_NAME + " 모듈을 찾을 수 없음.\n휴대폰 블루투스 설정에서 페어링 확인\n(Logcat에서 페어링된 장치 목록 확인)");
                scanButton.setEnabled(true);
            });
        }
    }

    //장치 연결
    private void connectToDevice() {
        if (targetDevice == null || !checkConnectPermission()) return;

        new Thread(() -> {
            try {
                bluetoothSocket = targetDevice.createRfcommSocketToServiceRecord(SPP_UUID);

                handler.post(() -> statusTextView.setText("장치 연결 중..."));

                bluetoothSocket.connect();
                setBluetoothConnected(true);

                Log.d(TAG, "블루투스 소켓 연결 성공");
                handler.post(() -> {
                    statusTextView.setText("✅ 블루투스 연결 성공. 데이터 수신 대기 중...");
                });

                connectedThread = new ConnectedThread(bluetoothSocket);
                connectedThread.start();
                Log.d(TAG, "블루투스 데이터 수신 스레드 시작됨");

            } catch (SecurityException e) {
                Log.e(TAG, "연결 권한 오류", e);
                closeAllConnections(); // 연결 실패 시 모든 연결 닫기 (복원됨)
                handler.post(() -> {
                    statusTextView.setText("연결 권한 오류");
                    scanButton.setEnabled(true);
                });
            } catch (IOException e) {
                Log.e(TAG, "소켓 연결 실패", e);
                closeAllConnections(); // 연결 실패 시 모든 연결 닫기 (복원됨)
                handler.post(() -> {
                    statusTextView.setText("❌ 블루투스 연결 실패: " + e.getMessage());
                    scanButton.setEnabled(true);
                });
            }
        }).start();
    }

    private void toggleTcpConnection() {
        // 테스트 모드: 블루투스 연결 없이도 TCP 연결 가능
        // if (!isBluetoothConnected) {
        //     Toast.makeText(this, "블루투스를 먼저 연결하세요.", Toast.LENGTH_SHORT).show();
        //     return;
        // }

        if (tcpSender != null) {
            stopTcpClient();
        } else {
            startTcpClient();
        }
    }

    private void startTcpClient() {
        if (tcpSender != null) return;

        if ("PC의_IP_주소".equals(PYTHON_SERVER_IP)) {
            Toast.makeText(this, "TCP 서버 IP를 MainActivity에 설정하세요.", Toast.LENGTH_LONG).show();
            return;
        }

        tcpSender = new TcpClientSender(PYTHON_SERVER_IP, PYTHON_SERVER_PORT);
        tcpSender.start();
        handler.post(() -> statusTextView.setText("TCP 서버 연결 시도 중..."));
        updateServerButtonState();
    }

    private void stopTcpClient() {
        TcpClientSender sender = tcpSender;
        if (sender == null) return;

        tcpSender = null;
        sender.closeConnection();
        setServerConnected(false);
        currentSessionId = null;
        loggedInUserId = null;
        handler.post(() -> statusTextView.setText("TCP 서버 연결이 중지되었습니다."));
        updateServerButtonState();
        updateAuthButtonState();
    }

    private void setBluetoothConnected(boolean connected) {
        isBluetoothConnected = connected;
        updateServerButtonState();
        updateConnectionBadge();
        if (!connected && resultTextView != null) {
            handler.post(() -> resultTextView.setText("서버 응답 없음"));
        }
    }

    private void updateServerButtonState() {
        handler.post(() -> applyServerButtonState());
    }

    private void applyServerButtonState() {
        if (serverButton == null) return;
        // 테스트 모드: 항상 활성화
        serverButton.setEnabled(true);
        // serverButton.setEnabled(isBluetoothConnected);
        serverButton.setText(tcpSender != null ? "TCP 연결 해제" : "TCP 서버 연결");
    }

    private void onTcpThreadStopped(TcpClientSender sender) {
        if (tcpSender == sender) {
            tcpSender = null;
            handler.post(() -> statusTextView.setText("TCP 서버 연결이 종료되었습니다."));
            updateServerButtonState();
        }
    }

    // 데이터 수신 스레드 (Bluetooth로부터 ECG 값 수신)
    private class ConnectedThread extends Thread {
        private final InputStream mmInStream;
        private final BufferedReader mmBufferReader;
        private final BluetoothSocket mmSocket;

        public ConnectedThread(BluetoothSocket socket) {
            this.mmSocket = socket;
            InputStream tmpIn = null;
            BufferedReader tmpReader = null;
            try {
                if (socket == null) {
                    Log.e(TAG, "BluetoothSocket이 null입니다.");
                } else if (!socket.isConnected()) {
                    Log.e(TAG, "BluetoothSocket이 연결되지 않았습니다.");
                } else {
                    Log.d(TAG, "BluetoothSocket 연결 상태 확인: 연결됨");
                    tmpIn = socket.getInputStream();
                    if (tmpIn == null) {
                        Log.e(TAG, "InputStream을 가져올 수 없습니다.");
                    } else {
                        Log.d(TAG, "InputStream 생성 성공, BufferedReader 생성 중...");
                        // 최소 버퍼 크기(1바이트)로 설정하여 즉시 처리되도록 함
                        tmpReader = new BufferedReader(new InputStreamReader(tmpIn, "UTF-8"), 1);
                        Log.d(TAG, "블루투스 InputStream 및 BufferedReader 생성 성공");
                    }
                }
            }
            catch (IOException e) {
                Log.e(TAG, "Input Stream 생성 실패", e);
            }
            mmInStream = tmpIn;
            mmBufferReader = tmpReader;
        }

        @SuppressLint("SetTextI18n")
        public void run() {
            if (mmBufferReader == null) {
                Log.e(TAG, "블루투스 InputStream이 null입니다. 연결을 확인하세요.");
                handler.post(() -> statusTextView.setText("❌ 블루투스 스트림 생성 실패"));
                return;
            }

            if (mmSocket == null || !mmSocket.isConnected()) {
                Log.e(TAG, "블루투스 소켓이 연결되지 않았습니다.");
                handler.post(() -> statusTextView.setText("❌ 블루투스 소켓 연결 안됨"));
                return;
            }

            Log.d(TAG, "블루투스 데이터 수신 스레드 시작 (소켓 연결됨: " + mmSocket.isConnected() + ")");
            handler.post(() -> statusTextView.setText("📡 블루투스 데이터 수신 대기 중..."));

            String line;
            int receivedCount = 0;
            int errorCount = 0;
            long lastLogTime = System.currentTimeMillis();
            long startTime = System.currentTimeMillis();
            long lastHeartbeat = System.currentTimeMillis();

            while (!Thread.currentThread().isInterrupted()) {
                try {
                    // 소켓 연결 상태 확인
                    if (!mmSocket.isConnected()) {
                        Log.w(TAG, "블루투스 소켓 연결이 끊어졌습니다.");
                        // 등록/로그인 모드 중이면 모드 종료
                        if (isRegisterMode || isLoginMode) {
                            isRegisterMode = false;
                            isLoginMode = false;
                            dummyDataSampleCount = 0;
                            stopDummyData();
                            handler.post(() -> {
                                hideProgress();
                                statusTextView.setText("❌ 블루투스 연결 끊김 - 등록/로그인 중단");
                                Toast.makeText(MainActivity.this, "❌ 블루투스 연결이 끊겨 등록/로그인이 중단되었습니다.", Toast.LENGTH_LONG).show();
                            });
                        }
                        break;
                    }

                    // 하트비트 로그 (10초마다, 데이터가 없어도)
                    long currentTime = System.currentTimeMillis();
                    if (currentTime - lastHeartbeat > 10000) {
                        double elapsed = (currentTime - startTime) / 1000.0;
                        Log.d(TAG, String.format("블루투스 수신 대기 중... (%.1f초 경과, 수신: %d개, 오류: %d개)", 
                            elapsed, receivedCount, errorCount));
                        lastHeartbeat = currentTime;
                    }

                    // readLine()은 블로킹되므로, 데이터가 오지 않으면 여기서 대기
                    // Arduino에서 데이터를 보내지 않으면 이 부분에서 멈춤
                    line = mmBufferReader.readLine();

                    if (line != null && !line.isEmpty()) {
                        receivedCount++;
                        String trimmedLine = line.trim();
                        
                        // 시작 메시지 무시
                        if (trimmedLine.contains("AD8232") || trimmedLine.contains("Started")) {
                            Log.d(TAG, "Arduino 시작 메시지 수신: " + trimmedLine);
                            continue;
                        }
                        
                        try {
                            // 문자열에서 정수로 변환
                            int ecgValue = Integer.parseInt(trimmedLine);
                            
                            // 데이터 범위 검증 (일반적인 ECG ADC 범위: 0-1023)
                            if (ecgValue < 0 || ecgValue > 4095) {
                                Log.w(TAG, "ECG 값이 범위를 벗어남: " + ecgValue + " (수신된 라인: " + trimmedLine + ")");
                                // 범위를 벗어나도 처리 (센서에 따라 다를 수 있음)
                            }

                            handler.post(() -> {
                                ecgValueTextView.setText("ECG 값: " + ecgValue);
                                addEntry(ecgValue);
                            });

                            // TCP로 전송 (등록/로그인 모드일 때만, 안정화 완료 후, 아직 수집 중일 때만)
                            if (tcpSender != null && (isRegisterMode || isLoginMode) && !isStabilizing && dummyDataSampleCount < requiredSamples) {
                                tcpSender.sendData(ecgValue);
                                dummyDataSampleCount++; // 블루투스 데이터도 카운트
                                
                                // 진행률 업데이트 (100개마다)
                                if (dummyDataSampleCount % 100 == 0) {
                                    int progress = (int) ((dummyDataSampleCount * 100.0) / requiredSamples);
                                    progress = Math.min(95, progress); // 최대 95%까지 (수집 중)
                                    updateProgress(progress, dummyDataSampleCount + " / " + requiredSamples + " 샘플");
                                }
                                
                                // 필요한 샘플 수를 모두 수집했으면
                                if (dummyDataSampleCount >= requiredSamples) {
                                    // 샘플 수집 완료 표시
                                    handler.post(() -> {
                                        if (isRegisterMode) {
                                            showProgress("등록", "샘플 데이터 수집 완료 - 서버 처리 대기 중...", 100, requiredSamples + " / " + requiredSamples + " 샘플");
                                            statusTextView.setText("샘플 데이터 수집 완료 - 서버에서 등록 처리 중...");
                                            Toast.makeText(MainActivity.this, "📊 샘플 데이터 수집 완료하였습니다. 서버 처리 중...", Toast.LENGTH_SHORT).show();
                                        } else if (isLoginMode) {
                                            showProgress("로그인", "샘플 데이터 수집 완료 - 서버 처리 대기 중...", 100, requiredSamples + " / " + requiredSamples + " 샘플");
                                            statusTextView.setText("샘플 데이터 수집 완료 - 서버에서 로그인 처리 중...");
                                            Toast.makeText(MainActivity.this, "📊 샘플 데이터 수집 완료하였습니다. 서버 처리 중...", Toast.LENGTH_SHORT).show();
                                        }
                                    });
                                    // 수집 완료 후 서버에 완료 신호 전송 (딜레이 추가하여 마지막 데이터가 도착할 시간 확보)
                                    handler.postDelayed(() -> {
                                        if (tcpSender != null) {
                                            tcpSender.sendCommand("COMPLETE");
                                            Log.d(TAG, "블루투스 데이터 수집 완료 (" + requiredSamples + "개). 서버에 완료 신호 전송.");
                                        }
                                    }, 500); // 500ms 딜레이
                                }
                            }
                            // 모드가 아니면 서버로 전송하지 않음 (그래프만 표시)
                            // 등록/로그인 모드이고 이미 1000개 수집 완료했으면 전송하지 않음
                            
                            // 주기적으로 로그 출력 (5초마다)
                            currentTime = System.currentTimeMillis();
                            if (currentTime - lastLogTime > 5000) {
                                double elapsed = (currentTime - startTime) / 1000.0;
                                double rate = receivedCount / elapsed;
                                String modeInfo = "";
                                if (isRegisterMode || isLoginMode) {
                                    modeInfo = String.format(", 등록/로그인 모드: %d/%d 샘플", dummyDataSampleCount, requiredSamples);
                                }
                                Log.d(TAG, String.format("블루투스 데이터 수신 중... (총 %d개, %.1f초 경과, %.1f개/초, 현재 값: %d%s)", 
                                    receivedCount, elapsed, rate, ecgValue, modeInfo));
                                lastLogTime = currentTime;
                            }

                        } catch (NumberFormatException e) {
                            errorCount++;
                            Log.w(TAG, "수신된 데이터가 숫자가 아님: [" + trimmedLine + "] (길이: " + trimmedLine.length() + ", 오류 횟수: " + errorCount + ")");
                            
                            // 너무 많은 오류가 발생하면 경고
                            if (errorCount > 10 && receivedCount == 0) {
                                Log.e(TAG, "데이터 수신 실패: 숫자가 아닌 데이터만 수신되고 있습니다. Arduino 코드를 확인하세요.");
                                handler.post(() -> statusTextView.setText("⚠️ 데이터 포맷 오류: 숫자가 아닌 데이터 수신"));
                            }
                        }
                    } else if (line == null) {
                        // 스트림이 닫혔을 때
                        Log.w(TAG, "블루투스 스트림이 null을 반환했습니다. 연결이 끊어진 것 같습니다.");
                        // 등록/로그인 모드 중이면 모드 종료
                        if (isRegisterMode || isLoginMode) {
                            isRegisterMode = false;
                            isLoginMode = false;
                            dummyDataSampleCount = 0;
                            stopDummyData();
                            handler.post(() -> {
                                hideProgress();
                                statusTextView.setText("❌ 블루투스 연결 끊김 - 등록/로그인 중단");
                                Toast.makeText(MainActivity.this, "❌ 블루투스 연결이 끊겨 등록/로그인이 중단되었습니다.", Toast.LENGTH_LONG).show();
                            });
                        }
                        break;
                    } else {
                        // 빈 라인 - 정상일 수 있음
                        Log.v(TAG, "빈 라인 수신 (정상)");
                    }
                } catch (IOException e) {
                    Log.e(TAG, "블루투스 읽기 오류", e);
                    errorCount++;
                    
                    // 일시적 오류인지 확인 (연결 끊김인지)
                    if (!mmSocket.isConnected()) {
                        Log.e(TAG, "블루투스 연결이 끊어졌습니다.");
                        // 등록/로그인 모드 중이면 모드 종료
                        if (isRegisterMode || isLoginMode) {
                            isRegisterMode = false;
                            isLoginMode = false;
                            dummyDataSampleCount = 0;
                            stopDummyData();
                            handler.post(() -> {
                                hideProgress();
                                statusTextView.setText("❌ 블루투스 연결 끊김 - 등록/로그인 중단");
                                Toast.makeText(MainActivity.this, "❌ 블루투스 연결이 끊겨 등록/로그인이 중단되었습니다.", Toast.LENGTH_LONG).show();
                            });
                        }
                        closeAllConnections();
                        handler.post(() -> statusTextView.setText("❌ 블루투스 연결 끊김: " + e.getMessage()));
                        break;
                    }
                    
                    // 일시적 오류인 경우 잠시 대기 후 재시도
                    if (errorCount < 5) {
                        try {
                            Thread.sleep(100);
                        } catch (InterruptedException ie) {
                            break;
                        }
                    } else {
                        Log.e(TAG, "너무 많은 오류 발생. 연결을 종료합니다.");
                        // 등록/로그인 모드 중이면 모드 종료
                        if (isRegisterMode || isLoginMode) {
                            isRegisterMode = false;
                            isLoginMode = false;
                            dummyDataSampleCount = 0;
                            stopDummyData();
                            handler.post(() -> {
                                hideProgress();
                                statusTextView.setText("❌ 블루투스 오류 - 등록/로그인 중단");
                                Toast.makeText(MainActivity.this, "❌ 블루투스 오류로 등록/로그인이 중단되었습니다.", Toast.LENGTH_LONG).show();
                            });
                        }
                        closeAllConnections();
                        handler.post(() -> statusTextView.setText("❌ 블루투스 오류가 너무 많습니다."));
                        break;
                    }
                }
            }
            
            double totalTime = (System.currentTimeMillis() - startTime) / 1000.0;
            Log.d(TAG, String.format("블루투스 데이터 수신 스레드 종료 (총 %d개 수신, 오류 %d개, %.1f초 실행)", 
                receivedCount, errorCount, totalTime));
            
            if (receivedCount == 0) {
                handler.post(() -> statusTextView.setText("⚠️ 블루투스 연결됨, 하지만 데이터 수신 없음"));
            }
        }
    }

    // ✨ TCP 클라이언트 스레드 (Python 서버와 통신 및 응답 수신) - 송/수신 분리 구조 (복원됨)
    private class TcpClientSender extends Thread {
        private final String SERVER_IP;
        private final int SERVER_PORT;
        private Socket tcpSocket;
        private PrintWriter out;
        private BufferedReader in;
        private volatile boolean isRunning = true;
        // 큐 크기를 제한하지 않는 LinkedBlockingQueue 사용
        private final BlockingQueue<Integer> dataQueue = new LinkedBlockingQueue<>();
        private static final String TCP_TAG = "ECG_TCP_CLIENT";

        public TcpClientSender(String ip, int port) {
            this.SERVER_IP = ip;
            this.SERVER_PORT = port;
        }

        public void sendData(int data) {
            // offer를 사용하여 큐에 데이터를 추가합니다.
            dataQueue.offer(data);
            
            // 큐 크기 모니터링 (딜레이 확인용)
            int queueSize = dataQueue.size();
            if (queueSize > 100) {
                Log.w(TCP_TAG, "큐 크기 경고: " + queueSize + "개 대기 중 (네트워크 딜레이 발생 가능)");
            }
        }
        
        public void sendCommand(String command) {
            // 명령어 전송 (CMD: 접두사 추가) - 별도 스레드에서 실행
            new Thread(() -> {
                try {
                    if (out != null) {
                        out.println("CMD:" + command);
                        Log.d(TCP_TAG, "Sent command: CMD:" + command);
                    } else {
                        Log.w(TCP_TAG, "Cannot send command - output stream is null");
                    }
                } catch (Exception e) {
                    Log.e(TCP_TAG, "Error sending command: " + e.getMessage());
                }
            }).start();
        }

        @Override
        public void run() {
            while (isRunning) {
                try {
                    // 1. 연결이 끊겼거나 닫혔으면 새로 연결 시도
                    if (tcpSocket == null || tcpSocket.isClosed()) {
                        attemptConnection();
                    }

                    // 2. 연결이 성공하면 송신 및 수신 스레드 시작
                    if (tcpSocket != null && tcpSocket.isConnected()) {
                        setServerConnected(true);
                        handler.post(() -> statusTextView.setText("✅ TCP 서버 연결 성공. 데이터 스트리밍 시작."));

                        // 송신 및 수신 스레드 시작 (메인 스레드를 블로킹하지 않음)
                        Thread senderThread = new Thread(this::dataSender, "TCP-Sender");
                        Thread receiverThread = new Thread(this::resultReceiver, "TCP-Receiver");

                        senderThread.start();
                        receiverThread.start();

                        // 두 스레드가 종료될 때까지 대기
                        senderThread.join();
                        receiverThread.join();
                    }

                } catch (InterruptedException e) {
                    Log.w(TCP_TAG, "TCP 메인 스레드 인터럽트됨.");
                    Thread.currentThread().interrupt();
                    isRunning = false;
                } catch (Exception e) {
                    Log.e(TCP_TAG, "TCP 메인 루프 오류: " + e.getMessage());
                    handler.post(() -> statusTextView.setText("❌ TCP 연결 실패. 재시도 중..."));
                    // 오류 발생 시 연결을 닫고, 잠시 후 재시도를 위해 루프를 계속함
                    closeConnectionInternal();
                    try { TimeUnit.SECONDS.sleep(3); } catch (InterruptedException ignore) { }
                }
            }
            MainActivity.this.onTcpThreadStopped(TcpClientSender.this);
        }

        // 연결 시도 로직 분리
        private void attemptConnection() throws IOException {
            handler.post(() -> statusTextView.setText("TCP 연결 시도 중..."));
            Log.d(TCP_TAG, "Attempting to connect to " + SERVER_IP + ":" + SERVER_PORT);

            tcpSocket = new Socket();
            // 5초 타임아웃 설정
            tcpSocket.connect(new InetSocketAddress(SERVER_IP, SERVER_PORT), 5000);

            out = new PrintWriter(new BufferedWriter(new OutputStreamWriter(tcpSocket.getOutputStream())), true);
            in = new BufferedReader(new InputStreamReader(tcpSocket.getInputStream()));
            Log.d(TCP_TAG, "Connection established.");
        }


        // 데이터를 Python 서버로 보내는 서브 루틴
        private void dataSender() {
            while (!Thread.currentThread().isInterrupted() && tcpSocket != null && tcpSocket.isConnected() && isRunning) {
                try {
                    // 큐에서 데이터 꺼내기 (데이터가 들어올 때까지 대기 - Blocking)
                    int dataToSend = dataQueue.take();

                    // 데이터를 줄바꿈 문자와 함께 전송
                    out.println(dataToSend);
                    Log.v(TCP_TAG, "Sent raw ECG: " + dataToSend + " (큐 크기: " + dataQueue.size() + ")");

                } catch (InterruptedException e) {
                    Log.w(TCP_TAG, "Data sender interrupted.");
                    Thread.currentThread().interrupt();
                    break;
                }
            }
            Log.d(TCP_TAG, "Data sender stopped.");
        }

        // 처리된 결과(JSON)를 Python 서버로부터 받는 서브 루틴
        private void resultReceiver() {
            try {
                String processedLine;
                while (!Thread.currentThread().isInterrupted() && in != null && tcpSocket.isConnected() && isRunning) {
                    processedLine = in.readLine();

                    if (processedLine == null) {
                        // 서버에서 연결을 닫았을 때
                        Log.d(TCP_TAG, "Server closed the connection gracefully.");
                        break;
                    }

                    if (!processedLine.isEmpty()) {
                        handleServerResponse(processedLine); // ✨ 서버 응답 처리 함수 호출
                    }
                }
            } catch (IOException e) {
                Log.e(TCP_TAG, "Result receiver I/O error: " + e.getMessage());
            } finally {
                Log.d(TCP_TAG, "Result receiver stopped. Attempting reconnection...");
                // 수신 스레드가 종료되면 전체 TCP 연결을 닫고 재연결 루프를 다시 돌게 함
                closeConnectionInternal();
            }
        }

        // 서버 응답 (JSON) 처리
        private void handleServerResponse(String jsonResponse) {
            try {
                Log.d(TCP_TAG, "서버 응답 수신: " + jsonResponse);
                JSONObject json = new JSONObject(jsonResponse);

                String status = json.optString("status", "error");
                String message = json.optString("message", "No message");
                Log.d(TCP_TAG, "응답 상태: " + status + ", 메시지: " + message);

                // 사용자 목록 응답 처리 (JSON에 users 배열이 있는 경우)
                if (json.has("users")) {
                    handleUserListResponse(json);
                    return;
                }
                
                // 사용자 삭제 응답 처리 (명시적으로 "삭제"와 "사용자"가 모두 포함된 경우만)
                if (message.contains("삭제") && message.contains("사용자")) {
                    handleUserDeleteResponse(json);
                    return;
                }
                
                // 인증 관련 응답 처리 (우선 처리)
                if (json.has("session_id") || "auth_failed".equals(status) || 
                    message.contains("등록") || message.contains("로그") || 
                    "connected".equals(status)) {
                    handleAuthResponse(json);
                    return;
                }

                // 일반 ECG 처리 성공 (인증과 무관한 경우)
                if ("success".equals(status)) {
                    // 서버에서 생성된 서명 또는 특징 벡터를 추출
                    String signatureHash = json.optString("signature_hash", "");
                    double qualityScore = json.optDouble("quality_score", 0);

                    // 요약 정보 가져오기
                    JSONObject summary = json.optJSONObject("summary");
                    double heartRate = summary != null ? summary.optDouble("heart_rate", 0) : 0;
                    int numBeats = summary != null ? summary.optInt("num_beats", 0) : 0;

                    handler.post(() -> {
                        String resultText = "✅ ECG 처리 완료\n";
                        resultText += "심박수: " + String.format("%.1f", heartRate) + " BPM\n";
                        resultText += "비트 수: " + numBeats + "\n";
                        resultText += "품질: " + String.format("%.0f", qualityScore) + "점\n";
                        if (!signatureHash.isEmpty()) {
                            resultText += "서명: " + signatureHash.substring(0, Math.min(16, signatureHash.length())) + "...";
                        }
                        resultTextView.setText(resultText);
                    });

                } else if ("ready".equals(status)) {
                    // 등록/로그인 준비 상태 - 데이터 수집 시작
                    String mode = json.optString("mode", "");
                    int serverRequiredSamples = json.optInt("required_samples", 3000);
                    // 서버에서 받은 값과 3000 중 큰 값을 사용 (최소 3000개 보장)
                    requiredSamples = Math.max(3000, serverRequiredSamples);
                    dummyDataSampleCount = 0; // 샘플 카운터 리셋
                    
                    // 모드 플래그 설정
                    if ("register".equals(mode)) {
                        isRegisterMode = true;
                        isLoginMode = false;
                    } else if ("login".equals(mode)) {
                        isLoginMode = true;
                        isRegisterMode = false;
                    }
                    
                    handler.post(() -> {
                        if ("register".equals(mode)) {
                            statusTextView.setText("등록 모드 시작 - ECG 데이터 수집 중...");
                            showProgress("등록", "등록 모드 시작 - ECG 데이터 수집 중...", 0, "0 / " + requiredSamples + " 샘플");
                        } else if ("login".equals(mode)) {
                            statusTextView.setText("로그인 모드 시작 - ECG 데이터 수집 중...");
                            showProgress("로그인", "로그인 모드 시작 - ECG 데이터 수집 중...", 0, "0 / " + requiredSamples + " 샘플");
                        }
                    });
                } else if (!"error".equals(status)) {
                    handler.post(() -> resultTextView.setText(message));
                } else {
                    // 에러 발생 시 진행 상태 숨기기
                    hideProgress();
                    handler.post(() -> Toast.makeText(MainActivity.this, "❌ " + message, Toast.LENGTH_LONG).show());
                }

            } catch (JSONException e) {
                Log.e(TAG, "JSON 파싱 실패", e);
                handler.post(() -> Toast.makeText(MainActivity.this, "응답 JSON 파싱 실패", Toast.LENGTH_LONG).show());
            }
        }

        // 실제 암호화 로직 (Placeholder) (복원됨)
        private String encryptData(String data) {
            // Java 8 이상에서 Base64 인코딩 사용
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                return Base64.getEncoder().encodeToString(data.getBytes());
            } else {
                // 하위 버전 호환을 위해 Toast 대신 기본 로직만 유지
                return "Base64 not supported below API 26";
            }
        }

        // 내부적으로 연결을 정리하고 루프를 계속 유지 (재연결 시도용)
        private void closeConnectionInternal() {
            try {
                if (out != null) out.close();
                if (in != null) in.close();
                if (tcpSocket != null && !tcpSocket.isClosed()) tcpSocket.close();
            } catch (IOException e) {
                Log.e(TCP_TAG, "TCP 소켓 내부 닫기 실패", e);
            } finally {
                tcpSocket = null;
                out = null;
                in = null;
            }
        }

        // 외부에서 호출되는 최종 종료 메서드
        public void closeConnection() {
            isRunning = false;
            closeConnectionInternal();
            // 큐에 대기 중인 take()를 해제하기 위해 인터럽트 호출
            this.interrupt();
        }
    }


    private void closeSocket() {
        if (bluetoothSocket != null) {
            try { bluetoothSocket.close(); } catch (IOException e) { Log.e(TAG, "소켓 닫기 실패", e); }
            bluetoothSocket = null;
        }
    }

    // 모든 연결 (블루투스, TCP 스레드)을 닫는 함수 (복원됨)
    private void closeAllConnections() {
        closeSocket();
        if (connectedThread != null) {
            connectedThread.interrupt();
            connectedThread = null;
        }
        stopTcpClient();
        setBluetoothConnected(false);
    }

    private boolean checkConnectPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
            return ActivityCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
        return true;
    }

    @Override
    protected void onStop() {
        super.onStop();
        stopDummyData();
        closeAllConnections(); // 모든 연결 정리 (복원됨)
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        stopDummyData();
        closeAllConnections(); // 모든 연결 정리 (복원됨)
    }
}