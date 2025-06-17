#!/bin/bash

# M2M RSP Zone Deployment Script
# Usage: ./zone-deploy.sh [deploy|teardown|restart] [zone-a|zone-b|zone-c|all]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ACTION=""
ZONE=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="${SCRIPT_DIR}/k8s"

# Zone files
ZONE_FILES=(
    "m2m-rsp-zone-a.yaml"
    "m2m-rsp-zone-b.yaml"
    "m2m-rsp-zone-c.yaml"
)

# Zone names
ZONES=("zone-a" "zone-b" "zone-c")

# Functions
print_usage() {
    echo -e "${BLUE}M2M RSP Zone Deployment Script${NC}"
    echo ""
    echo "Usage: $0 [ACTION] [ZONE]"
    echo ""
    echo "Actions:"
    echo "  deploy       - Deploy the specified zone(s)"
    echo "  teardown     - Remove the specified zone(s)"
    echo "  teardown-all - Remove all zones (no zone parameter needed)"
    echo "  restart      - Teardown and redeploy the specified zone(s)"
    echo ""
    echo "Zones:"
    echo "  zone-a    - Deploy only zone-a (us-east-1)"
    echo "  zone-b    - Deploy only zone-b (us-west-2)"
    echo "  zone-c    - Deploy only zone-c (eu-central-1)"
    echo "  all       - Deploy all zones (default)"
    echo ""
    echo "Examples:"
    echo "  $0 deploy all"
    echo "  $0 teardown zone-a"
    echo "  $0 teardown-all"
    echo "  $0 restart zone-b"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_microk8s() {
    if ! command -v microk8s &>/dev/null; then
        log_error "microk8s is not installed or not in PATH"
        exit 1
    fi

    if ! microk8s status --wait-ready --timeout 30 >/dev/null 2>&1; then
        log_error "microk8s is not running or not ready"
        exit 1
    fi

    log_info "microk8s is ready"
}

deploy_zone() {
    local zone_file="$1"
    local zone_name="$2"

    log_info "Deploying ${zone_name}..."

    if [ ! -f "${K8S_DIR}/${zone_file}" ]; then
        log_error "Zone file ${zone_file} not found in ${K8S_DIR}"
        return 1
    fi

    if microk8s kubectl apply -f "${K8S_DIR}/${zone_file}"; then
        log_success "Successfully deployed ${zone_name}"
    else
        log_error "Failed to deploy ${zone_name}"
        return 1
    fi
}

teardown_zone() {
    local zone_file="$1"
    local zone_name="$2"

    log_info "Tearing down ${zone_name}..."

    if [ ! -f "${K8S_DIR}/${zone_file}" ]; then
        log_warning "Zone file ${zone_file} not found in ${K8S_DIR}, trying to delete namespace directly"
        microk8s kubectl delete namespace "m2m-rsp-${zone_name}" --ignore-not-found=true
        return 0
    fi

    if microk8s kubectl delete -f "${K8S_DIR}/${zone_file}" --ignore-not-found=true; then
        log_success "Successfully tore down ${zone_name}"
    else
        log_error "Failed to tear down ${zone_name}"
        return 1
    fi
}

restart_zone() {
    local zone_file="$1"
    local zone_name="$2"

    log_info "Restarting ${zone_name}..."
    teardown_zone "$zone_file" "$zone_name"
    sleep 5 # Wait a bit for cleanup
    deploy_zone "$zone_file" "$zone_name"
}

get_zone_files() {
    local zone="$1"
    case "$zone" in
    "zone-a")
        echo "m2m-rsp-zone-a.yaml"
        ;;
    "zone-b")
        echo "m2m-rsp-zone-b.yaml"
        ;;
    "zone-c")
        echo "m2m-rsp-zone-c.yaml"
        ;;
    "all")
        echo "${ZONE_FILES[@]}"
        ;;
    *)
        log_error "Unknown zone: $zone"
        exit 1
        ;;
    esac
}

get_zone_names() {
    local zone="$1"
    case "$zone" in
    "zone-a" | "zone-b" | "zone-c")
        echo "$zone"
        ;;
    "all")
        echo "${ZONES[@]}"
        ;;
    *)
        log_error "Unknown zone: $zone"
        exit 1
        ;;
    esac
}

show_status() {
    log_info "Checking M2M RSP deployment status..."
    echo ""

    for zone in "${ZONES[@]}"; do
        echo -e "${BLUE}=== Zone: $zone ===${NC}"
        namespace="m2m-rsp-$zone"

        if microk8s kubectl get namespace "$namespace" >/dev/null 2>&1; then
            echo "Namespace: $namespace (EXISTS)"
            echo "Pods:"
            microk8s kubectl get pods -n "$namespace" -o wide 2>/dev/null || echo "  No pods found"
            echo "Services:"
            microk8s kubectl get services -n "$namespace" 2>/dev/null || echo "  No services found"
        else
            echo "Namespace: $namespace (NOT FOUND)"
        fi
        echo ""
    done
}

# Parse arguments
if [ $# -eq 0 ]; then
    print_usage
    exit 1
fi

ACTION="$1"
ZONE="${2:-all}"

# Validate action
case "$ACTION" in
"deploy" | "teardown" | "restart" | "status" | "teardown-all") ;;
*)
    log_error "Invalid action: $ACTION"
    print_usage
    exit 1
    ;;
esac

# Validate zone
case "$ZONE" in
"zone-a" | "zone-b" | "zone-c" | "all") ;;
*)
    log_error "Invalid zone: $ZONE"
    print_usage
    exit 1
    ;;
esac

# Main execution
log_info "Starting M2M RSP Zone Management"
log_info "Action: $ACTION, Zone(s): $ZONE"

check_microk8s

case "$ACTION" in
"status")
    show_status
    ;;
"deploy")
    zone_files=($(get_zone_files "$ZONE"))
    zone_names=($(get_zone_names "$ZONE"))

    for i in "${!zone_files[@]}"; do
        deploy_zone "${zone_files[$i]}" "${zone_names[$i]}"
    done

    log_success "Deployment completed for $ZONE"
    ;;
"teardown-all")
    zone_files=("${ZONE_FILES[@]}")
    zone_names=("${ZONES[@]}")

    for i in "${!zone_files[@]}"; do
        teardown_zone "${zone_files[$i]}" "${zone_names[$i]}"
    done

    log_success "Teardown completed for all zones"
    ;;

"restart")
    zone_files=($(get_zone_files "$ZONE"))
    zone_names=($(get_zone_names "$ZONE"))

    for i in "${!zone_files[@]}"; do
        restart_zone "${zone_files[$i]}" "${zone_names[$i]}"
    done

    log_success "Restart completed for $ZONE"
    ;;
esac

log_info "Operation completed successfully"
