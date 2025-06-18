#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    if ! command -v microk8s >/dev/null 2>&1; then
        print_error "MicroK8s is not installed"
        echo "Install with: sudo snap install microk8s --classic"
        exit 1
    fi
    
    if ! microk8s status --wait-ready; then
        print_error "MicroK8s is not ready"
        exit 1
    fi
    
    print_success "Prerequisites check passed"
}

# Function to deploy the zones
deploy_zones() {
    print_status "Deploying M2M RSP zones..."
    
    # Get script directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Deploy each zone
    print_status "Deploying Zone A (Seoul)..."
    microk8s kubectl apply -f "$SCRIPT_DIR/k8s/m2m-rsp-zone-a.yaml"
    
    print_status "Deploying Zone B (Virginia)..."
    microk8s kubectl apply -f "$SCRIPT_DIR/k8s/m2m-rsp-zone-b.yaml"
    
    print_status "Deploying Zone C (Ireland)..."
    microk8s kubectl apply -f "$SCRIPT_DIR/k8s/m2m-rsp-zone-c.yaml"
    
    print_success "All zones deployed"
}

# Function to wait for deployments
wait_for_deployments() {
    print_status "Waiting for deployments to be ready..."
    
    # Wait for Zone A
    print_status "Waiting for Zone A (Seoul) deployment..."
    microk8s kubectl wait --for=condition=available --timeout=300s deployment/m2m-rsp-server -n m2m-rsp-zone-a
    
    # Wait for Zone B
    print_status "Waiting for Zone B (Virginia) deployment..."
    microk8s kubectl wait --for=condition=available --timeout=300s deployment/m2m-rsp-server -n m2m-rsp-zone-b
    
    # Wait for Zone C
    print_status "Waiting for Zone C (Ireland) deployment..."
    microk8s kubectl wait --for=condition=available --timeout=300s deployment/m2m-rsp-server -n m2m-rsp-zone-c
    
    print_success "All deployments are ready"
}

# Function to deploy Istio configuration
deploy_istio_config() {
    print_status "Deploying Istio service mesh configuration..."
    
    # Get script directory (if not already set)
    if [ -z "$SCRIPT_DIR" ]; then
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    fi
    
    # Check if Istio is installed
    if ! microk8s kubectl get namespace istio-system >/dev/null 2>&1; then
        print_error "Istio is not installed. Please run setup-microk8s-istio.sh first"
        exit 1
    fi
    
    # Apply Istio configuration
    microk8s kubectl apply -f "$SCRIPT_DIR/k8s/istio-latency-simulation.yaml"
    
    # Apply gateway if it exists
    if [ -f "$SCRIPT_DIR/k8s/istio-gateway.yaml" ]; then
        microk8s kubectl apply -f "$SCRIPT_DIR/k8s/istio-gateway.yaml"
    fi
    
    print_success "Istio configuration deployed"
}

# Function to show service information
show_service_info() {
    print_status "Gathering service information..."
    
    echo ""
    echo "================================="
    echo "  M2M RSP Service Mesh Deployment"
    echo "================================="
    echo ""
    
    # Zone A (Seoul)
    echo "📍 Zone A - Seoul, South Korea (LOCAL)"
    echo "   Region: ap-northeast-2"
    echo "   Replicas: 2"
    ZONE_A_NODEPORT=$(microk8s kubectl get svc m2m-rsp-nodeport -n m2m-rsp-zone-a -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "N/A")
    echo "   NodePort: http://localhost:$ZONE_A_NODEPORT"
    echo "   Expected Latency: <10ms (local)"
    echo ""
    
    # Zone B (Virginia)
    echo "🌎 Zone B - Virginia, USA (FAR)"
    echo "   Region: us-east-1"
    echo "   Replicas: 3"
    ZONE_B_NODEPORT=$(microk8s kubectl get svc m2m-rsp-nodeport -n m2m-rsp-zone-b -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "N/A")
    echo "   NodePort: http://localhost:$ZONE_B_NODEPORT"
    echo "   Simulated Latency: ~180ms RTT"
    echo ""
    
    # Zone C (Ireland)
    echo "🌍 Zone C - Ireland, Europe (FAR)"
    echo "   Region: eu-west-1"
    echo "   Replicas: 2"
    ZONE_C_NODEPORT=$(microk8s kubectl get svc m2m-rsp-nodeport -n m2m-rsp-zone-c -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "N/A")
    echo "   NodePort: http://localhost:$ZONE_C_NODEPORT"
    echo "   Simulated Latency: ~280ms RTT"
    echo ""
    
    # Istio Gateway
    echo "🌐 Istio Service Mesh Gateway"
    ISTIO_GATEWAY_PORT=$(microk8s kubectl get svc istio-ingressgateway -n istio-system -o jsonpath='{.spec.ports[?(@.name=="http2")].nodePort}' 2>/dev/null || echo "N/A")
    echo "   Gateway: http://localhost:$ISTIO_GATEWAY_PORT"
    echo "   Load Balancing: 70% Seoul, 20% Virginia, 10% Ireland"
    echo ""
    
    # Test commands
    echo "🎯 Test Commands:"
    echo "=================="
    echo ""
    echo "# Test local Seoul zone (fast response):"
    echo "curl -w \"@curl-format.txt\" http://localhost:$ZONE_A_NODEPORT/status/smdp"
    echo ""
    echo "# Test Virginia zone (with simulated 180ms latency):"
    echo "curl -w \"@curl-format.txt\" http://localhost:$ZONE_B_NODEPORT/status/smdp"
    echo ""
    echo "# Test Ireland zone (with simulated 280ms latency):"
    echo "curl -w \"@curl-format.txt\" http://localhost:$ZONE_C_NODEPORT/status/smdp"
    echo ""
    echo "# Test through Istio Gateway with geographic routing:"
    echo "curl -w \"@curl-format.txt\" http://localhost:$ISTIO_GATEWAY_PORT/status/smdp"
    echo ""
    
    # Create curl format file for timing
    cat > curl-format.txt << 'EOF'
     time_namelookup:  %{time_namelookup}\n
        time_connect:  %{time_connect}\n
     time_appconnect:  %{time_appconnect}\n
    time_pretransfer:  %{time_pretransfer}\n
       time_redirect:  %{time_redirect}\n
  time_starttransfer:  %{time_starttransfer}\n
                     ----------\n
          time_total:  %{time_total}\n
EOF
    
    echo "📊 Monitoring Commands:"
    echo "======================"
    echo ""
    echo "# Watch all pods:"
    echo "microk8s kubectl get pods -A -w"
    echo ""
    echo "# Check application logs:"
    echo "microk8s kubectl logs -f deployment/m2m-rsp-server -n m2m-rsp-zone-a"
    echo ""
    echo "# Check Istio proxy logs (for latency simulation):"
    echo "microk8s kubectl logs -f deployment/m2m-rsp-server -c istio-proxy -n m2m-rsp-zone-b"
    echo ""
    echo "# Enable and access Kiali dashboard:"
    echo "microk8s enable kiali"
    echo "microk8s kubectl port-forward -n istio-system svc/kiali 20001:20001"
    echo "# Then open: http://localhost:20001 (admin/admin)"
    echo ""
}

# Function to run tests
run_tests() {
    if [ "$1" = "--test" ]; then
        print_status "Running connectivity tests..."
        
        # Test each zone
        for zone in a b c; do
            nodeport=$(microk8s kubectl get svc m2m-rsp-nodeport -n m2m-rsp-zone-$zone -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "")
            if [ ! -z "$nodeport" ]; then
                print_status "Testing Zone $zone (port $nodeport)..."
                if curl -s -o /dev/null -w "%{http_code}" http://localhost:$nodeport/status/smdp | grep -q "200"; then
                    print_success "Zone $zone is responding"
                else
                    print_warning "Zone $zone is not responding"
                fi
            fi
        done
    fi
}

# Main execution
main() {
    echo "🚀 M2M RSP Multi-Zone Service Mesh Deployment"
    echo "=============================================="
    echo ""
    
    check_prerequisites
    deploy_zones
    wait_for_deployments
    deploy_istio_config
    
    # Wait a bit for Istio to process the configuration
    sleep 10
    
    show_service_info
    run_tests "$1"
    
    print_success "Deployment completed successfully!"
    echo ""
    echo "🌟 Your M2M RSP service mesh is now running with:"
    echo "   • 1 local zone in Seoul (fast)"
    echo "   • 2 remote zones with realistic latency simulation"
    echo "   • Istio service mesh for traffic management"
    echo "   • Circuit breakers and retry policies"
    echo ""
    echo "📈 Perfect for benchmarking M2M communication patterns!"
}

# Run with test flag if requested
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: $0 [--test]"
    echo ""
    echo "Options:"
    echo "  --test    Run connectivity tests after deployment"
    echo "  --help    Show this help message"
    exit 0
fi

main "$1" 