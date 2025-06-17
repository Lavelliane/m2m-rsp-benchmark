#!/bin/bash

# Enhanced M2M RSP Zone Deployment Script with Traffic Control Integration
# Usage: ./zone-deploy-enhanced.sh [deploy|teardown|restart] [zone-a|zone-b|zone-c|all] [--tc-scenario SCENARIO]

set -e

# Source the original zone-deploy.sh functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/zone-deploy.sh" 2>/dev/null || {
    # If sourcing fails, define essential variables
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
    K8S_DIR="${SCRIPT_DIR}/k8s"
    ZONE_FILES=("m2m-rsp-zone-a.yaml" "m2m-rsp-zone-b.yaml" "m2m-rsp-zone-c.yaml")
    ZONES=("zone-a" "zone-b" "zone-c")
}

# Enhanced configuration
TC_ENABLED=false
TC_SCENARIO="normal"
MONITORING_ENABLED=false
HEALTH_CHECK_ENABLED=true

print_enhanced_usage() {
    echo -e "${BLUE}Enhanced M2M RSP Zone Deployment Script${NC}"
    echo ""
    echo "Usage: $0 [ACTION] [ZONE] [OPTIONS]"
    echo ""
    echo "Actions:"
    echo "  deploy    - Deploy the specified zone(s)"
    echo "  teardown  - Remove the specified zone(s)"
    echo "  restart   - Teardown and redeploy the specified zone(s)"
    echo "  status    - Show zone and network status"
    echo ""
    echo "Zones:"
    echo "  zone-a    - Deploy only zone-a (us-east-1)"
    echo "  zone-b    - Deploy only zone-b (us-west-2)"
    echo "  zone-c    - Deploy only zone-c (eu-central-1)"
    echo "  all       - Deploy all zones (default)"
    echo ""
    echo "Options:"
    echo "  --tc-scenario SCENARIO  - Enable traffic control with scenario"
    echo "                           (normal, degraded, poor, unstable)"
    echo "  --monitor              - Enable continuous monitoring"
    echo "  --no-healthcheck       - Skip health checks"
    echo ""
    echo "Examples:"
    echo "  $0 deploy all --tc-scenario normal"
    echo "  $0 deploy zone-a --tc-scenario poor --monitor"
    echo "  $0 restart zone-b --tc-scenario unstable"
    echo "  $0 teardown all"
}

log_enhanced() {
    echo -e "${GREEN}[ENHANCED]${NC} $1"
}

check_tc_requirements() {
    if [[ $EUID -ne 0 ]] && [[ "$TC_ENABLED" == true ]]; then
        log_error "Traffic control simulation requires root privileges. Please run with sudo."
        exit 1
    fi
    
    if [[ "$TC_ENABLED" == true ]] && ! command -v tc &> /dev/null; then
        log_error "tc (traffic control) is not installed. Install with: apt-get install iproute2"
        exit 1
    fi
}

setup_traffic_control() {
    if [[ "$TC_ENABLED" == true ]]; then
        log_enhanced "Setting up traffic control with scenario: $TC_SCENARIO"
        
        if [[ -f "${SCRIPT_DIR}/tc-network-sim.sh" ]]; then
            bash "${SCRIPT_DIR}/tc-network-sim.sh" start "$TC_SCENARIO"
        else
            log_error "Traffic control script not found: ${SCRIPT_DIR}/tc-network-sim.sh"
            exit 1
        fi
    fi
}

cleanup_traffic_control() {
    if [[ "$TC_ENABLED" == true ]]; then
        log_enhanced "Cleaning up traffic control rules"
        
        if [[ -f "${SCRIPT_DIR}/tc-network-sim.sh" ]]; then
            bash "${SCRIPT_DIR}/tc-network-sim.sh" stop
        fi
    fi
}

wait_for_pods_ready() {
    local zone_name="$1"
    local namespace="m2m-rsp-$zone_name"
    local timeout=120  # 2 minutes
    local elapsed=0
    
    log_info "Waiting for pods in $namespace to be ready..."
    
    while [ $elapsed -lt $timeout ]; do
        local ready_pods=$(microk8s kubectl get pods -n "$namespace" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
        local total_pods=$(microk8s kubectl get pods -n "$namespace" --no-headers 2>/dev/null | wc -l)
        
        if [[ $ready_pods -gt 0 ]] && [[ $ready_pods -eq $total_pods ]]; then
            log_success "All pods in $namespace are ready ($ready_pods/$total_pods)"
            return 0
        fi
        
        echo -n "."
        sleep 5
        elapsed=$((elapsed + 5))
    done
    
    log_warning "Timeout waiting for pods in $namespace to be ready"
    return 1
}

perform_health_check() {
    local zone_name="$1"
    local port_map=( ["zone-a"]="30080" ["zone-b"]="30081" ["zone-c"]="30082" )
    local port=${port_map[$zone_name]}
    
    if [[ "$HEALTH_CHECK_ENABLED" == false ]]; then
        return 0
    fi
    
    log_info "Performing health check for $zone_name on port $port..."
    
    local max_attempts=10
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s --connect-timeout 5 "http://localhost:$port/status/smdp" > /dev/null 2>&1; then
            log_success "$zone_name health check passed (attempt $attempt)"
            return 0
        fi
        
        echo -n "."
        sleep 3
        attempt=$((attempt + 1))
    done
    
    log_error "$zone_name health check failed after $max_attempts attempts"
    return 1
}

enhanced_deploy_zone() {
    local zone_file="$1"
    local zone_name="$2"
    
    log_enhanced "Enhanced deployment of ${zone_name}..."
    
    # Deploy using original function
    deploy_zone "$zone_file" "$zone_name"
    
    # Wait for pods to be ready
    wait_for_pods_ready "$zone_name"
    
    # Perform health check
    perform_health_check "$zone_name"
    
    log_success "Enhanced deployment of $zone_name completed"
}

enhanced_show_status() {
    log_enhanced "Enhanced M2M RSP Status Report"
    echo ""
    
    # Show original status
    show_status
    
    # Show traffic control status if enabled
    if [[ "$TC_ENABLED" == true ]]; then
        echo ""
        log_enhanced "Traffic Control Status:"
        bash "${SCRIPT_DIR}/tc-network-sim.sh" status
    fi
    
    # Show detailed zone health
    echo ""
    log_enhanced "Zone Health Summary:"
    local zones_healthy=0
    local total_zones=0
    
    for zone in "${ZONES[@]}"; do
        local port_map=( ["zone-a"]="30080" ["zone-b"]="30081" ["zone-c"]="30082" )
        local port=${port_map[$zone]}
        
        echo -n "  $zone: "
        if curl -s --connect-timeout 2 "http://localhost:$port/status/smdp" > /dev/null 2>&1; then
            echo -e "${GREEN}Healthy${NC}"
            zones_healthy=$((zones_healthy + 1))
        else
            echo -e "${RED}Unhealthy${NC}"
        fi
        total_zones=$((total_zones + 1))
    done
    
    echo ""
    echo -e "Overall Health: $zones_healthy/$total_zones zones healthy"
    
    if [[ "$TC_ENABLED" == true ]]; then
        echo ""
        log_enhanced "Testing inter-zone latencies..."
        bash "${SCRIPT_DIR}/tc-network-sim.sh" test
    fi
}

start_monitoring() {
    if [[ "$MONITORING_ENABLED" == true ]]; then
        log_enhanced "Starting monitoring dashboard..."
        
        # Create a simple monitoring script
        cat > "${SCRIPT_DIR}/monitor-zones.sh" << 'EOF'
#!/bin/bash
while true; do
    clear
    echo "M2M RSP Multi-Zone Monitoring - $(date)"
    echo "========================================"
    
    for port in 30080 30081 30082; do
        zone_name=""
        case $port in
            30080) zone_name="zone-a (us-east-1)" ;;
            30081) zone_name="zone-b (us-west-2)" ;;
            30082) zone_name="zone-c (eu-central-1)" ;;
        esac
        
        echo ""
        echo "$zone_name:"
        if metrics=$(curl -s --connect-timeout 2 "http://localhost:$port/system-metrics" 2>/dev/null); then
            cpu=$(echo $metrics | jq -r '.cpu_percent // "N/A"' 2>/dev/null || echo "N/A")
            memory=$(echo $metrics | jq -r '.memory_mb // "N/A"' 2>/dev/null || echo "N/A")
            echo "  Status: Online | CPU: ${cpu}% | Memory: ${memory}MB"
        else
            echo "  Status: Offline"
        fi
    done
    
    sleep 5
done
EOF
        
        chmod +x "${SCRIPT_DIR}/monitor-zones.sh"
        nohup "${SCRIPT_DIR}/monitor-zones.sh" > /dev/null 2>&1 &
        MONITOR_PID=$!
        echo $MONITOR_PID > "${SCRIPT_DIR}/.monitor.pid"
        
        log_enhanced "Monitoring started with PID: $MONITOR_PID"
        log_enhanced "Stop monitoring with: kill $MONITOR_PID"
    fi
}

stop_monitoring() {
    if [[ -f "${SCRIPT_DIR}/.monitor.pid" ]]; then
        local pid=$(cat "${SCRIPT_DIR}/.monitor.pid")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            log_enhanced "Monitoring stopped (PID: $pid)"
        fi
        rm -f "${SCRIPT_DIR}/.monitor.pid"
    fi
}

# Parse arguments with enhanced options
TEMP=$(getopt -o h --long tc-scenario:,monitor,no-healthcheck,help -n 'zone-deploy-enhanced' -- "$@")
if [ $? != 0 ]; then
    print_enhanced_usage
    exit 1
fi

eval set -- "$TEMP"

while true; do
    case "$1" in
        --tc-scenario)
            TC_ENABLED=true
            TC_SCENARIO="$2"
            shift 2
            ;;
        --monitor)
            MONITORING_ENABLED=true
            shift
            ;;
        --no-healthcheck)
            HEALTH_CHECK_ENABLED=false
            shift
            ;;
        -h|--help)
            print_enhanced_usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Get positional arguments
ACTION="$1"
ZONE="${2:-all}"

# Validate action and zone (reuse original validation)
case "$ACTION" in
    "deploy"|"teardown"|"restart"|"status")
        ;;
    *)
        if [[ -z "$ACTION" ]]; then
            print_enhanced_usage
            exit 1
        fi
        log_error "Invalid action: $ACTION"
        print_enhanced_usage
        exit 1
        ;;
esac

case "$ZONE" in
    "zone-a"|"zone-b"|"zone-c"|"all")
        ;;
    *)
        log_error "Invalid zone: $ZONE"
        print_enhanced_usage
        exit 1
        ;;
esac

# Main execution with enhancements
log_enhanced "Starting Enhanced M2M RSP Zone Management"
log_enhanced "Action: $ACTION, Zone(s): $ZONE"

if [[ "$TC_ENABLED" == true ]]; then
    log_enhanced "Traffic Control: Enabled (Scenario: $TC_SCENARIO)"
fi

check_microk8s
check_tc_requirements

case "$ACTION" in
    "status")
        enhanced_show_status
        ;;
    "deploy")
        # Setup traffic control before deployment
        setup_traffic_control
        
        zone_files=($(get_zone_files "$ZONE"))
        zone_names=($(get_zone_names "$ZONE"))
        
        for i in "${!zone_files[@]}"; do
            enhanced_deploy_zone "${zone_files[$i]}" "${zone_names[$i]}"
        done
        
        # Start monitoring if enabled
        start_monitoring
        
        log_success "Enhanced deployment completed for $ZONE"
        
        if [[ "$TC_ENABLED" == true ]]; then
            echo ""
            log_enhanced "Traffic control active with scenario: $TC_SCENARIO"
            log_enhanced "Test latencies with: sudo bash tc-network-sim.sh test"
            log_enhanced "Stop traffic control with: sudo bash tc-network-sim.sh stop"
        fi
        ;;
    "teardown")
        # Stop monitoring
        stop_monitoring
        
        zone_files=($(get_zone_files "$ZONE"))
        zone_names=($(get_zone_names "$ZONE"))
        
        for i in "${!zone_files[@]}"; do
            teardown_zone "${zone_files[$i]}" "${zone_names[$i]}"
        done
        
        # Cleanup traffic control
        cleanup_traffic_control
        
        log_success "Enhanced teardown completed for $ZONE"
        ;;
    "restart")
        # Stop monitoring during restart
        stop_monitoring
        
        zone_files=($(get_zone_files "$ZONE"))
        zone_names=($(get_zone_names "$ZONE"))
        
        for i in "${!zone_files[@]}"; do
            teardown_zone "${zone_files[$i]}" "${zone_names[$i]}"
        done
        
        sleep 5  # Wait for cleanup
        
        # Setup traffic control before redeployment
        setup_traffic_control
        
        for i in "${!zone_files[@]}"; do
            enhanced_deploy_zone "${zone_files[$i]}" "${zone_names[$i]}"
        done
        
        # Restart monitoring if it was enabled
        start_monitoring
        
        log_success "Enhanced restart completed for $ZONE"
        ;;
esac

log_enhanced "Operation completed successfully"