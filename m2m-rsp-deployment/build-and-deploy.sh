#!/bin/bash

# M2M RSP Build and Deploy Script for microk8s
# This script builds the Docker image and deploys to microk8s

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="m2m-rsp-mock"
IMAGE_TAG="latest"
FULL_IMAGE_NAME="${IMAGE_NAME}:${IMAGE_TAG}"

log_info() {
    echo -e "${BLUE}[BUILD]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[BUILD]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[BUILD]${NC} $1"
}

log_error() {
    echo -e "${RED}[BUILD]${NC} $1"
}

print_usage() {
    echo -e "${BLUE}M2M RSP Build and Deploy Script${NC}"
    echo ""
    echo "Usage: $0 [ACTION]"
    echo ""
    echo "Actions:"
    echo "  build          - Build the Docker image only"
    echo "  deploy         - Build image and deploy all zones"
    echo "  deploy-zone    - Build image and deploy specific zone"
    echo "  rebuild        - Force rebuild image (no cache)"
    echo "  clean          - Remove built images"
    echo "  check          - Check if image exists"
    echo ""
    echo "Examples:"
    echo "  $0 build"
    echo "  $0 deploy"
    echo "  $0 deploy-zone zone-a"
    echo "  $0 rebuild"
}

check_requirements() {
    # Check if microk8s is available
    if ! command -v microk8s &> /dev/null; then
        log_error "microk8s is not installed or not in PATH"
        exit 1
    fi

    # Check if microk8s is running
    if ! microk8s status --wait-ready --timeout 30 > /dev/null 2>&1; then
        log_error "microk8s is not running or not ready"
        exit 1
    fi

    # Check if Docker is available (needed for building)
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    # Check if user can run docker commands
    if ! docker info > /dev/null 2>&1; then
        log_error "Cannot run docker commands. Please ensure Docker is running and user has permissions."
        log_info "Try: sudo usermod -aG docker \$USER && newgrp docker"
        exit 1
    fi

    log_info "Requirements check passed"
}

check_files() {
    log_info "Checking required files..."
    
    local required_files=("Dockerfile" "mock.py" "requirements.txt")
    
    for file in "${required_files[@]}"; do
        if [[ ! -f "${SCRIPT_DIR}/${file}" ]]; then
            log_error "Required file not found: ${file}"
            exit 1
        fi
    done
    
    log_success "All required files found"
}

build_image() {
    local rebuild=${1:-false}
    
    log_info "Building Docker image: ${FULL_IMAGE_NAME}"
    
    cd "${SCRIPT_DIR}"
    
    # Build arguments
    local build_args="--tag ${FULL_IMAGE_NAME}"
    
    if [[ "$rebuild" == "true" ]]; then
        build_args="$build_args --no-cache"
        log_info "Force rebuilding (no cache)"
    fi
    
    # Build the image
    if docker build $build_args .; then
        log_success "Docker image built successfully: ${FULL_IMAGE_NAME}"
    else
        log_error "Failed to build Docker image"
        exit 1
    fi
    
    # Show image info
    docker images "${IMAGE_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
}

import_to_microk8s() {
    log_info "Importing Docker image to microk8s..."
    
    # Check if microk8s has the image
    if microk8s ctr images list | grep -q "${FULL_IMAGE_NAME}"; then
        log_warning "Image already exists in microk8s, removing old version..."
        microk8s ctr images remove "${FULL_IMAGE_NAME}" || true
    fi
    
    # Save Docker image to tar
    local temp_file="/tmp/${IMAGE_NAME}.tar"
    log_info "Exporting Docker image to ${temp_file}"
    
    if docker save "${FULL_IMAGE_NAME}" -o "${temp_file}"; then
        log_success "Image exported successfully"
    else
        log_error "Failed to export Docker image"
        exit 1
    fi
    
    # Import to microk8s
    log_info "Importing image to microk8s..."
    if microk8s ctr images import "${temp_file}"; then
        log_success "Image imported to microk8s successfully"
    else
        log_error "Failed to import image to microk8s"
        exit 1
    fi
    
    # Clean up temp file
    rm -f "${temp_file}"
    
    # Verify import
    if microk8s ctr images list | grep -q "${FULL_IMAGE_NAME}"; then
        log_success "Image verification passed in microk8s"
    else
        log_error "Image verification failed in microk8s"
        exit 1
    fi
}

deploy_zones() {
    local zone=${1:-all}
    
    log_info "Deploying zones: $zone"
    
    # Use the existing zone deployment script
    if [[ -f "${SCRIPT_DIR}/zone-deploy.sh" ]]; then
        bash "${SCRIPT_DIR}/zone-deploy.sh" deploy "$zone"
    else
        log_error "Zone deployment script not found: ${SCRIPT_DIR}/zone-deploy.sh"
        exit 1
    fi
}

wait_for_deployment() {
    local namespace="$1"
    local timeout=120
    local elapsed=0
    
    log_info "Waiting for deployment in namespace: $namespace"
    
    while [ $elapsed -lt $timeout ]; do
        local ready_pods=$(microk8s kubectl get pods -n "$namespace" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
        local total_pods=$(microk8s kubectl get pods -n "$namespace" --no-headers 2>/dev/null | wc -l)
        
        if [[ $total_pods -gt 0 ]] && [[ $ready_pods -eq $total_pods ]]; then
            log_success "All pods ready in $namespace ($ready_pods/$total_pods)"
            return 0
        fi
        
        echo -n "."
        sleep 5
        elapsed=$((elapsed + 5))
    done
    
    log_warning "Timeout waiting for pods in $namespace"
    return 1
}

verify_deployment() {
    log_info "Verifying deployment..."
    
    local zones=("zone-a" "zone-b" "zone-c")
    local ports=(30080 30081 30082)
    
    for i in "${!zones[@]}"; do
        local zone="${zones[$i]}"
        local port="${ports[$i]}"
        local namespace="m2m-rsp-$zone"
        
        echo ""
        log_info "Checking $zone (port $port)..."
        
        # Check if namespace exists
        if ! microk8s kubectl get namespace "$namespace" > /dev/null 2>&1; then
            log_warning "Namespace $namespace does not exist"
            continue
        fi
        
        # Check pod status
        local pod_status=$(microk8s kubectl get pods -n "$namespace" --no-headers 2>/dev/null || echo "")
        if [[ -n "$pod_status" ]]; then
            echo "Pods:"
            echo "$pod_status" | while read line; do
                echo "  $line"
            done
        fi
        
        # Wait for deployment
        wait_for_deployment "$namespace"
        
        # Test HTTP endpoint
        log_info "Testing HTTP endpoint for $zone..."
        local max_attempts=10
        local attempt=1
        
        while [ $attempt -le $max_attempts ]; do
            if curl -s --connect-timeout 5 "http://localhost:$port/status/smdp" > /dev/null 2>&1; then
                log_success "$zone is responding on port $port"
                break
            fi
            
            if [ $attempt -eq $max_attempts ]; then
                log_warning "$zone is not responding on port $port after $max_attempts attempts"
            else
                echo -n "."
                sleep 3
            fi
            
            attempt=$((attempt + 1))
        done
    done
    
    echo ""
    log_success "Deployment verification completed"
}

check_image_exists() {
    log_info "Checking if image exists..."
    
    # Check in Docker
    if docker images "${IMAGE_NAME}" --format "{{.Repository}}:{{.Tag}}" | grep -q "${FULL_IMAGE_NAME}"; then
        log_success "Image found in Docker: ${FULL_IMAGE_NAME}"
    else
        log_warning "Image not found in Docker: ${FULL_IMAGE_NAME}"
    fi
    
    # Check in microk8s
    if microk8s ctr images list | grep -q "${FULL_IMAGE_NAME}"; then
        log_success "Image found in microk8s: ${FULL_IMAGE_NAME}"
    else
        log_warning "Image not found in microk8s: ${FULL_IMAGE_NAME}"
    fi
}

clean_images() {
    log_info "Cleaning up Docker images..."
    
    # Remove from Docker
    if docker images "${IMAGE_NAME}" --format "{{.Repository}}:{{.Tag}}" | grep -q "${FULL_IMAGE_NAME}"; then
        docker rmi "${FULL_IMAGE_NAME}" || true
        log_success "Removed image from Docker"
    fi
    
    # Remove from microk8s
    if microk8s ctr images list | grep -q "${FULL_IMAGE_NAME}"; then
        microk8s ctr images remove "${FULL_IMAGE_NAME}" || true
        log_success "Removed image from microk8s"
    fi
}

# Main execution
case "${1:-}" in
    "build")
        check_requirements
        check_files
        build_image
        import_to_microk8s
        ;;
    "deploy")
        check_requirements
        check_files
        build_image
        import_to_microk8s
        deploy_zones "all"
        verify_deployment
        ;;
    "deploy-zone")
        if [[ -z "$2" ]]; then
            log_error "Please specify zone: zone-a, zone-b, or zone-c"
            exit 1
        fi
        check_requirements
        check_files
        build_image
        import_to_microk8s
        deploy_zones "$2"
        verify_deployment
        ;;
    "rebuild")
        check_requirements
        check_files
        build_image "true"
        import_to_microk8s
        ;;
    "clean")
        clean_images
        ;;
    "check")
        check_image_exists
        ;;
    "help"|"--help"|"-h"|"")
        print_usage
        ;;
    *)
        log_error "Unknown action: $1"
        print_usage
        exit 1
        ;;
esac 