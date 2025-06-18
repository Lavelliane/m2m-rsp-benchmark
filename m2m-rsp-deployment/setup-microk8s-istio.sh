#!/bin/bash

set -e

echo "🚀 Setting up MicroK8s with Istio Service Mesh for M2M RSP Benchmark"

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to wait for condition
wait_for_condition() {
    local condition="$1"
    local timeout="${2:-300}"
    local interval="${3:-5}"
    local count=0
    
    while ! eval "$condition" && [ $count -lt $((timeout / interval)) ]; do
        echo "Waiting for: $condition"
        sleep $interval
        count=$((count + 1))
    done
    
    if [ $count -ge $((timeout / interval)) ]; then
        echo "❌ Timeout waiting for: $condition"
        return 1
    fi
    echo "✅ Condition met: $condition"
}

# Check if microk8s is installed
if ! command_exists microk8s; then
    echo "❌ MicroK8s is not installed. Please install it first:"
    echo "sudo snap install microk8s --classic"
    exit 1
fi

# Check if microk8s is ready
echo "🔍 Checking MicroK8s status..."
microk8s status --wait-ready

# Enable required addons
echo "📦 Enabling MicroK8s addons..."
microk8s enable dns
microk8s enable storage
microk8s enable metallb

# Wait for metallb configuration (you may need to configure IP range)
echo "⚠️  Please configure MetalLB IP range when prompted..."
echo "   Example: 192.168.1.240-192.168.1.250"

# Enable Istio
echo "🕸️ Enabling Istio service mesh..."
microk8s enable istio

# Wait for Istio to be ready
echo "⏳ Waiting for Istio control plane to be ready..."
wait_for_condition "microk8s kubectl get pods -n istio-system -l app=istiod | grep Running" 120

# Create alias for kubectl
echo "🔧 Setting up kubectl alias..."
if ! grep -q "alias kubectl='microk8s kubectl'" ~/.bashrc; then
    echo "alias kubectl='microk8s kubectl'" >> ~/.bashrc
fi

# Export kubeconfig for current session
export KUBECONFIG=""
alias kubectl='microk8s kubectl'

# Verify Istio installation
echo "✅ Verifying Istio installation..."
microk8s kubectl get pods -n istio-system

# Create namespaces with Istio injection
echo "🏗️ Creating namespaces with Istio sidecar injection..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
microk8s kubectl apply -f "$SCRIPT_DIR/k8s/m2m-rsp-zone-a.yaml"
microk8s kubectl apply -f "$SCRIPT_DIR/k8s/m2m-rsp-zone-b.yaml"
microk8s kubectl apply -f "$SCRIPT_DIR/k8s/m2m-rsp-zone-c.yaml"

# Wait for deployments to be ready
echo "⏳ Waiting for deployments to be ready..."
wait_for_condition "microk8s kubectl get pods -n m2m-rsp-zone-a | grep Running | wc -l | grep -q 2" 300
wait_for_condition "microk8s kubectl get pods -n m2m-rsp-zone-b | grep Running | wc -l | grep -q 3" 300
wait_for_condition "microk8s kubectl get pods -n m2m-rsp-zone-c | grep Running | wc -l | grep -q 2" 300

# Apply Istio configuration
echo "🌐 Applying Istio latency simulation configuration..."
microk8s kubectl apply -f "$SCRIPT_DIR/k8s/istio-latency-simulation.yaml"

# Create ingress gateway if needed
echo "🌉 Setting up Istio Gateway..."
if [ -f "$SCRIPT_DIR/k8s/istio-gateway.yaml" ]; then
    microk8s kubectl apply -f "$SCRIPT_DIR/k8s/istio-gateway.yaml"
fi

# Get service endpoints
echo "📋 Service Information:"
echo "===================="

# Zone A (Seoul - Local)
echo "📍 Zone A (Seoul, South Korea - LOCAL):"
ZONE_A_NODEPORT=$(microk8s kubectl get svc m2m-rsp-nodeport -n m2m-rsp-zone-a -o jsonpath='{.spec.ports[0].nodePort}')
echo "   NodePort: http://localhost:$ZONE_A_NODEPORT"
echo "   Expected latency: <10ms"

# Zone B (Virginia - Far)
echo "📍 Zone B (Virginia, USA - FAR):"
ZONE_B_NODEPORT=$(microk8s kubectl get svc m2m-rsp-nodeport -n m2m-rsp-zone-b -o jsonpath='{.spec.ports[0].nodePort}')
echo "   NodePort: http://localhost:$ZONE_B_NODEPORT"
echo "   Simulated latency: ~180ms RTT"

# Zone C (Ireland - Far)
echo "📍 Zone C (Ireland, Europe - FAR):"
ZONE_C_NODEPORT=$(microk8s kubectl get svc m2m-rsp-nodeport -n m2m-rsp-zone-c -o jsonpath='{.spec.ports[0].nodePort}')
echo "   NodePort: http://localhost:$ZONE_C_NODEPORT"
echo "   Simulated latency: ~280ms RTT"

# Istio Gateway
echo "🌐 Istio Gateway:"
ISTIO_GATEWAY_PORT=$(microk8s kubectl get svc istio-ingressgateway -n istio-system -o jsonpath='{.spec.ports[?(@.name=="http2")].nodePort}')
if [ ! -z "$ISTIO_GATEWAY_PORT" ]; then
    echo "   Gateway: http://localhost:$ISTIO_GATEWAY_PORT"
    echo "   Routing: 70% Seoul, 20% Virginia, 10% Ireland"
fi

echo ""
echo "🎯 Testing Commands:"
echo "==================="
echo "# Test Seoul zone (fast):"
echo "curl -H 'x-preferred-zone: seoul' http://localhost:$ISTIO_GATEWAY_PORT/status/smdp"
echo ""
echo "# Test Virginia zone (with 180ms simulated latency):"
echo "curl -H 'x-fallback-region: americas' http://localhost:$ISTIO_GATEWAY_PORT/status/smdp"
echo ""
echo "# Test Ireland zone (with 280ms simulated latency):"
echo "curl -H 'x-fallback-region: europe' http://localhost:$ISTIO_GATEWAY_PORT/status/smdp"
echo ""
echo "# Test default routing (geographic preference):"
echo "curl http://localhost:$ISTIO_GATEWAY_PORT/status/smdp"

echo ""
echo "🔍 Monitoring Commands:"
echo "======================"
echo "# Watch pods:"
echo "microk8s kubectl get pods -A -w"
echo ""
echo "# Check Istio proxy logs:"
echo "microk8s kubectl logs -f deployment/m2m-rsp-server -c istio-proxy -n m2m-rsp-zone-a"
echo ""
echo "# Istio dashboard (if enabled):"
echo "microk8s kubectl port-forward -n istio-system svc/kiali 20001:20001"
echo "# Then open: http://localhost:20001"

echo ""
echo "✅ Setup complete! Your service mesh is ready with realistic latency simulation."
echo "📊 Seoul zone will respond quickly (~5-10ms)"
echo "🌍 Remote zones (Virginia & Ireland) have realistic latency (180ms & 280ms)" 