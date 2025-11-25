package com.example.ecgapp;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
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
import android.widget.Button;
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

public class MainActivity extends AppCompatActivity {


    private static final String TAG = "ECG_APP_CLASSIC";
    private static final int REQUEST_ALL_PERMISSIONS = 1;

    private static final String TARGET_DEVICE_NAME = "HC-06";
    private static final UUID SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");

    private TextView statusTextView;
    private Button scanButton;
    private TextView ecgValueTextView;
    private LineChart ecgChart;
    private LineDataSet dataSet;
    private int dataIndex = 0; // X축(시간)을 나타낼 인덱스
    private static final int MAX_DATA_POINTS = 500; // 화면에 표시 데이터 최대 개수
    private BluetoothAdapter bluetoothAdapter;
    private BluetoothSocket bluetoothSocket;
    private BluetoothDevice targetDevice;
    private ConnectedThread connectedThread;
    private final Handler handler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        statusTextView = findViewById(R.id.statusTextView);
        scanButton = findViewById(R.id.scanButton);
        ecgValueTextView = findViewById(R.id.ecgValueTextView);

        // LineChart 객체 초기화
        ecgChart = findViewById(R.id.ecgChart);
        initChart(); // 그래프 초기화 메서드 호출

        scanButton.setOnClickListener(v -> {
            if (checkConnectPermission()) {
                connectToPairedDevice();
            }
        });
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

        dataSet.setColor(ContextCompat.getColor(this, android.R.color.holo_blue_light));
        dataSet.setLineWidth(1.5f);
        dataSet.setMode(LineDataSet.Mode.CUBIC_BEZIER);

        LineData lineData = new LineData(dataSet);
        ecgChart.setData(lineData);

        ecgChart.getDescription().setEnabled(false);
        ecgChart.setTouchEnabled(false);
        ecgChart.getLegend().setEnabled(false); // 범례 숨김

        XAxis xAxis = ecgChart.getXAxis();
        xAxis.setPosition(XAxis.XAxisPosition.BOTTOM);
        xAxis.setDrawLabels(false);
        xAxis.setDrawGridLines(true);

        ecgChart.getAxisLeft().setAxisMinimum(0f);
        ecgChart.getAxisLeft().setAxisMaximum(1024f);
        ecgChart.getAxisRight().setEnabled(false);

        ecgChart.invalidate();
    }

    //데이터 추가 및 그래프 갱신 메서드
    private void addEntry(int value) {
        //(X축: dataIndex, Y축: value)
        Entry newEntry = new Entry(dataIndex, value);
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

            for (BluetoothDevice device : pairedDevices) {
                if (TARGET_DEVICE_NAME.equals(device.getName())) {
                    targetDevice = device;
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
            connectToDevice();
        } else {
            handler.post(() -> {
                statusTextView.setText("❌ " + TARGET_DEVICE_NAME + " 모듈을 찾을 수 없음. 휴대폰 블루투스 설정에서 페어링 확인");
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

                handler.post(() -> {
                    statusTextView.setText("✅ 연결 성공");
                });

                connectedThread = new ConnectedThread(bluetoothSocket);
                connectedThread.start();

            } catch (SecurityException e) {
                Log.e(TAG, "연결 권한 오류", e);
                closeSocket();
                handler.post(() -> {
                    statusTextView.setText("연결 권한 오류");
                    scanButton.setEnabled(true);
                });
            } catch (IOException e) {
                Log.e(TAG, "소켓 연결 실패", e);
                closeSocket();
                handler.post(() -> {
                    statusTextView.setText("❌ 연결 실패: " + e.getMessage());
                    scanButton.setEnabled(true);
                });
            }
        }).start();
    }

    //데이터 수신 스레드
    private class ConnectedThread extends Thread {
        private final InputStream mmInStream;
        private final BufferedReader mmBufferReader;

        public ConnectedThread(BluetoothSocket socket) {
            InputStream tmpIn = null;
            BufferedReader tmpReader = null;
            try {
                tmpIn = socket.getInputStream();
                tmpReader = new BufferedReader(new InputStreamReader(tmpIn));
            }
            catch (IOException e) {
                Log.e(TAG, "Input Stream 생성 실패", e);
            }
            mmInStream = tmpIn;
            mmBufferReader = tmpReader;
        }

        @SuppressLint("SetTextI18n")
        public void run() {
            if (mmBufferReader == null) return;

            String line;

            while (!Thread.currentThread().isInterrupted()) {
                try {
                    line = mmBufferReader.readLine();

                    if (line != null && !line.isEmpty()) {
                        try {
                            // 문자열에서 정수로 변환
                            int ecgValue = Integer.parseInt(line.trim());

                            handler.post(() -> {
                                ecgValueTextView.setText("ECG 값: " + ecgValue);
                                addEntry(ecgValue);
                            });

                        } catch (NumberFormatException e) {
                            Log.w(TAG, "수신된 데이터가 숫자가 아님: " + line);
                        }
                    }
                } catch (IOException e) {
                    Log.e(TAG, "연결 끊김", e);
                    closeSocket();
                    handler.post(() -> statusTextView.setText("❌ 연결 끊김"));
                    break;
                }
            }
        }
    }

    private void closeSocket() {
        if (bluetoothSocket != null) {
            try { bluetoothSocket.close(); } catch (IOException e) { Log.e(TAG, "소켓 닫기 실패", e); }
            bluetoothSocket = null;
        }
    }

    private boolean checkConnectPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
            return ActivityCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
        return true;
    }

    @Override
    protected void onStop() {
        super.onStop();
        closeSocket();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        closeSocket();
        if (connectedThread != null) connectedThread.interrupt();
    }
}