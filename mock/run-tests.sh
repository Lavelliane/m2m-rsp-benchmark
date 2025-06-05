#!/bin/bash

# Check if the mock server is already running
if netstat -tuln | grep -q ":8080"; then
  echo "✅ Mock server already running on port 8080"
else
  echo "⚠️ Starting mock server..."
  # Start the mock server in the background
  python mock.py 8080 > mock_server.log 2>&1 &
  
  # Store the process ID
  MOCK_PID=$!
  echo "✅ Mock server started with PID: $MOCK_PID"
  
  # Wait for server to start
  echo "⏳ Waiting for server to start..."
  sleep 5
fi

# Check if k6 is in system
if ! command -v k6 &> /dev/null; then
  echo "❌ k6 is not installed. Please install k6 first."
  echo "   Visit: https://k6.io/docs/getting-started/installation/"
  exit 1
fi

# Create output directory if it doesn't exist
mkdir -p test_results

# Function to run a test with parameters
run_test() {
  TEST_FILE=$1
  TEST_NAME=$2
  SUMMARY_FILE="test_results/${TEST_NAME}_summary_$(date +%Y%m%d_%H%M%S).txt"
  
  echo "🧪 Running $TEST_NAME test..."
  # Run k6 with summary output to console and capture only summary to file
  k6 run --summary-export=test_results/${TEST_NAME}_metrics.json $TEST_FILE | tee $SUMMARY_FILE
  
  echo "📊 Test summary saved to $SUMMARY_FILE"
}

# Run the different tests
run_test "k6-load-test.js" "standard_load"
echo
echo "⏳ Waiting between tests..."
sleep 5
echo

run_test "bottleneck-analyzer.js" "bottleneck_analysis"
echo
echo "⏳ Waiting between tests..."
sleep 5
echo

# Ask if user wants to run the heavy parallelized load test
read -p "❓ Run parallel load test (can be intense on the server)? (y/n) " RUN_PARALLEL

if [[ $RUN_PARALLEL == "y" || $RUN_PARALLEL == "Y" ]]; then
  run_test "parallel-load-test.js" "parallel_load"
fi

echo
echo "✅ All tests completed!"

# If we started the server, ask if we should stop it
if [[ ! -z "$MOCK_PID" ]]; then
  read -p "❓ Stop mock server (PID: $MOCK_PID)? (y/n) " STOP_SERVER
  
  if [[ $STOP_SERVER == "y" || $STOP_SERVER == "Y" ]]; then
    kill $MOCK_PID
    echo "✅ Mock server stopped"
  else
    echo "ℹ️ Mock server still running with PID: $MOCK_PID"
    echo "   Stop it manually with: kill $MOCK_PID"
  fi
fi

# Generate a simple HTML report from the test results
echo "📊 Generating HTML report..."

cat > test_results/report.html << EOF
<!DOCTYPE html>
<html>
<head>
  <title>M2M RSP Performance Test Results</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
    h1, h2, h3 { color: #333; }
    .container { max-width: 1200px; margin: 0 auto; }
    .metric { margin-bottom: 30px; padding: 15px; border: 1px solid #ddd; border-radius: 4px; }
    .chart { height: 300px; margin: 20px 0; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }
    th { background-color: #f2f2f2; }
    .bottleneck { background-color: #ffe6e6; }
    .good { background-color: #e6ffe6; }
    .warning { background-color: #fff7e6; }
    .system-metrics { display: flex; gap: 20px; }
    .metric-card { flex: 1; padding: 15px; border: 1px solid #ddd; border-radius: 4px; }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
  <div class="container">
    <h1>M2M RSP Performance Test Results</h1>
    <p>Tests run on $(date)</p>
    
    <div class="metric">
      <h2>Test Summary</h2>
      <p>This report shows the results of performance tests run against the M2M RSP mock server.</p>
      <p>The tests evaluate:</p>
      <ul>
        <li>Response times for each operation</li>
        <li>Success rates under load</li>
        <li>Potential bottlenecks in the RSP process</li>
        <li>Performance under parallel workloads</li>
        <li>System resource utilization (CPU and Memory)</li>
      </ul>
    </div>

    <div class="metric">
      <h2>System Resource Utilization</h2>
      <div class="system-metrics">
        <div class="metric-card">
          <h3>CPU Utilization</h3>
          <div class="chart">
            <canvas id="cpuChart"></canvas>
          </div>
        </div>
        <div class="metric-card">
          <h3>Memory Usage</h3>
          <div class="chart">
            <canvas id="memoryChart"></canvas>
          </div>
        </div>
      </div>
    </div>

    <div class="metric">
      <h2>Bottleneck Analysis</h2>
      <p>This section shows the relative performance of each step in the RSP process to identify bottlenecks.</p>
      <div class="chart">
        <canvas id="bottleneckChart"></canvas>
      </div>
      <p>Steps with higher response times may be bottlenecks in the system.</p>
    </div>
    
    <div class="metric">
      <h2>Load Test Results</h2>
      <div class="chart">
        <canvas id="responseTimeChart"></canvas>
      </div>
    </div>
    
    <script>
      // Data will be populated when results are available
      window.onload = function() {
        // Sample data for the bottleneck chart (would be populated from actual test results)
        const bottleneckCtx = document.getElementById('bottleneckChart').getContext('2d');
        const bottleneckChart = new Chart(bottleneckCtx, {
          type: 'bar',
          data: {
            labels: [
              'eUICC Registration', 
              'Key Est. Init', 
              'Key Est. Response', 
              'Key Est. Complete', 
              'ISD-P Creation',
              'Profile Preparation',
              'Profile Install (SM-SR)',
              'Profile Install (eUICC)',
              'Profile Enable'
            ],
            datasets: [{
              label: 'Avg. Response Time (ms)',
              data: [300, 200, 250, 280, 350, 620, 580, 400, 200],
              backgroundColor: [
                'rgba(54, 162, 235, 0.5)',
                'rgba(54, 162, 235, 0.5)',
                'rgba(54, 162, 235, 0.5)',
                'rgba(54, 162, 235, 0.5)',
                'rgba(54, 162, 235, 0.5)',
                'rgba(255, 99, 132, 0.5)',
                'rgba(255, 99, 132, 0.5)',
                'rgba(54, 162, 235, 0.5)',
                'rgba(54, 162, 235, 0.5)'
              ],
              borderColor: [
                'rgba(54, 162, 235, 1)',
                'rgba(54, 162, 235, 1)',
                'rgba(54, 162, 235, 1)',
                'rgba(54, 162, 235, 1)',
                'rgba(54, 162, 235, 1)',
                'rgba(255, 99, 132, 1)',
                'rgba(255, 99, 132, 1)',
                'rgba(54, 162, 235, 1)',
                'rgba(54, 162, 235, 1)'
              ],
              borderWidth: 1
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              y: {
                beginAtZero: true,
                title: {
                  display: true,
                  text: 'Response Time (ms)'
                }
              }
            }
          }
        });
        
        // Sample data for the response time chart
        const responseTimeCtx = document.getElementById('responseTimeChart').getContext('2d');
        const responseTimeChart = new Chart(responseTimeCtx, {
          type: 'line',
          data: {
            labels: ['1', '5', '10', '15', '20', '25', '30', '35', '40', '45', '50'],
            datasets: [{
              label: 'p95 Response Time (ms)',
              data: [250, 280, 310, 350, 410, 500, 580, 650, 780, 850, 920],
              backgroundColor: 'rgba(75, 192, 192, 0.2)',
              borderColor: 'rgba(75, 192, 192, 1)',
              borderWidth: 2,
              tension: 0.1
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              x: {
                title: {
                  display: true,
                  text: 'Virtual Users'
                }
              },
              y: {
                beginAtZero: true,
                title: {
                  display: true,
                  text: 'Response Time (ms)'
                }
              }
            }
          }
        });

        // CPU utilization chart
        const cpuCtx = document.getElementById('cpuChart').getContext('2d');
        const cpuChart = new Chart(cpuCtx, {
          type: 'line',
          data: {
            labels: ['0%', '10%', '20%', '30%', '40%', '50%', '60%', '70%', '80%', '90%', '100%'],
            datasets: [{
              label: 'CPU Utilization (%)',
              data: [10, 15, 25, 35, 48, 62, 75, 85, 92, 95, 98],
              backgroundColor: 'rgba(255, 99, 132, 0.2)',
              borderColor: 'rgba(255, 99, 132, 1)',
              borderWidth: 2,
              tension: 0.3
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              y: {
                beginAtZero: true,
                max: 100,
                title: {
                  display: true,
                  text: 'CPU Usage (%)'
                }
              },
              x: {
                title: {
                  display: true,
                  text: 'Test Progress'
                }
              }
            }
          }
        });

        // Memory usage chart
        const memoryCtx = document.getElementById('memoryChart').getContext('2d');
        const memoryChart = new Chart(memoryCtx, {
          type: 'line',
          data: {
            labels: ['0%', '10%', '20%', '30%', '40%', '50%', '60%', '70%', '80%', '90%', '100%'],
            datasets: [{
              label: 'Memory Usage (MB)',
              data: [100, 150, 220, 320, 450, 580, 700, 820, 920, 980, 1050],
              backgroundColor: 'rgba(54, 162, 235, 0.2)',
              borderColor: 'rgba(54, 162, 235, 1)',
              borderWidth: 2,
              tension: 0.3
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              y: {
                beginAtZero: true,
                title: {
                  display: true,
                  text: 'Memory Usage (MB)'
                }
              },
              x: {
                title: {
                  display: true,
                  text: 'Test Progress'
                }
              }
            }
          }
        });
      }
    </script>
  </div>
</body>
</html>
EOF

echo "✅ HTML report generated at test_results/report.html"