#!/bin/bash

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

show_error() {
    echo -e "${RED}✗ ERROR:${NC} $1"
    exit 1
}

show_success() {
    echo -e "${GREEN}✓${NC} $1"
}

free_port() {
    local port=$1
    local container=$(docker ps --format '{{.Names}}' --filter "publish=$port")
    if [ ! -z "$container" ]; then
        echo -e "${YELLOW}Port $port is in use by container $container. Stopping container...${NC}"
        docker stop $container >/dev/null 2>&1
        sleep 2
        show_success "Freed port $port"
    fi
}

wait_for_service() {
    local service=$1
    local port=$2
    local retries=36  
    local count=0
    
    echo -e "${YELLOW}Waiting for $service to initialize...${NC}"
    while [ $count -lt $retries ]; do
        echo -e "${YELLOW}Attempt $(($count+1))/$retries: Checking $service on port $port...${NC}"
        
        local response=$(curl -s -w "\n%{http_code}" http://localhost:$port 2>&1)
        local status_code=$(echo "$response" | tail -n1)
        local content=$(echo "$response" | sed \$d)
        
        if [[ "$status_code" =~ ^[23] ]]; then
            show_success "$service is now responding!"
            return 0
        else
            echo -e "${YELLOW}Response from $service: Status $status_code${NC}"
            if [ ! -z "$content" ]; then
                echo -e "${YELLOW}Error details: $content${NC}"
            fi
        fi
        
        if ! docker ps | grep -q "$service"; then
            echo -e "${RED}Warning: $service container is not running!${NC}"
            echo -e "${YELLOW}Container logs:${NC}"
            local service_lower=$(echo "$service" | tr '[:upper:]' '[:lower:]')
            docker-compose logs --tail=20 $service_lower
        fi
        
        sleep 5
        count=$((count+1))
    done
    
    show_error "$service is not responding after 180 seconds. Please check 'docker-compose logs $service' for details."
}

if [ "$EUID" -ne 0 ]; then 
    show_error "Please run as root (use: sudo ./setup.sh)"
fi

if ! grep -q "Raspberry Pi" /proc/cpuinfo && ! grep -q "raspberrypi" /proc/device-tree/model 2>/dev/null; then
    show_error "This script is designed for Raspberry Pi. Current system not detected as a Raspberry Pi."
fi

echo -e "${BLUE}=== Checking required files ===${NC}"
for file in "compose.yaml" "grafana/dashboards/dashboard.json" "grafana/dashboards/dashboard.yaml" "grafana/datasources/datasource.yaml" "prometheus/prometheus.yaml"; do
    if [ ! -f "$file" ]; then
        show_error "Missing required file: $file. Please ensure you're in the correct directory."
    fi
done
show_success "All required files found"

echo -e "\n${BLUE}=== Checking internet connection ===${NC}"
if ! ping -c 1 8.8.8.8 >/dev/null 2>&1; then
    show_error "No internet connection detected. Please check your network connection."
fi
show_success "Internet connection verified"

echo -e "\n${BLUE}=== Checking available disk space ===${NC}"
FREE_SPACE=$(df -k / | awk 'NR==2 {print $4}')
if [ "$FREE_SPACE" -lt 1048576 ]; then  
    show_error "Insufficient disk space. Need at least 1GB free space."
fi
show_success "Sufficient disk space available"

echo -e "\n${BLUE}=== Checking port availability ===${NC}"
for port in 3000 9090 9100; do
    if netstat -tuln | grep -q ":$port "; then
        free_port $port
    fi
done
show_success "Required ports are available"

echo -e "\n${BLUE}=== Starting Installation ===${NC}"

echo -e "\n${YELLOW}1.${NC} Installing required packages..."
if ! apt-get update 2>/dev/null; then
    show_error "Failed to update package list. Check your internet connection or try 'sudo apt-get update' manually."
fi

if ! apt-get install -y docker.io docker-compose 2>/dev/null; then
    show_error "Failed to install Docker. Please try 'sudo apt-get install docker.io docker-compose' manually."
fi
show_success "Required packages installed"

echo -e "\n${YELLOW}2.${NC} Setting up Docker..."
if ! systemctl start docker; then
    show_error "Failed to start Docker service"
fi

if ! systemctl enable docker; then
    show_error "Failed to enable Docker service"
fi

if ! usermod -aG docker $SUDO_USER; then
    show_error "Failed to add user to Docker group"
fi
show_success "Docker configured successfully"

IP_ADDRESS=$(hostname -I | awk '{print $1}')
if [ -z "$IP_ADDRESS" ]; then
    show_error "Failed to detect IP address"
fi

echo -e "\n${YELLOW}3.${NC} Starting monitoring services..."
echo -e "${YELLOW}Setting correct permissions on configuration files...${NC}"

chmod -R 755 ./prometheus
chmod -R 755 ./grafana

CURRENT_USER=$SUDO_USER

echo -e "${YELLOW}Cleaning up any existing containers...${NC}"
docker-compose down --remove-orphans

if ! docker-compose up -d --force-recreate; then
    show_error "Failed to start containers. Check 'docker-compose logs' for details."
fi

echo -e "${YELLOW}Verifying containers started...${NC}"
for service in "grafana" "prometheus" "node-exporter"; do
    if ! docker ps | grep -q "$service"; then
        show_error "Service $service failed to start. Check 'docker-compose logs $service'"
    fi
    show_success "$service container is running"
done

echo -e "\n${BLUE}=== Verifying service endpoints ===${NC}"
echo -e "${YELLOW}Checking Prometheus container logs:${NC}"
docker-compose logs prometheus

wait_for_service "Grafana" "3000"
wait_for_service "Prometheus" "9090"

count=0
retries=12
while ! curl -s http://localhost:9100/metrics >/dev/null && [ $count -lt $retries ]; do
    echo -e "${YELLOW}Waiting for Node Exporter to respond ($(($retries-$count)) attempts remaining)...${NC}"
    sleep 5
    count=$((count+1))
done

if [ $count -eq $retries ]; then
    show_error "Node Exporter is not responding after 60 seconds"
fi
show_success "Node Exporter is responding"

echo -e "\n${YELLOW}5.${NC} Creating status script..."
if ! cat > "status.sh" << 'EOF'
#!/bin/bash
echo "=== Monitoring Status ==="
docker ps
echo -e "\nTo view logs: docker-compose logs"
EOF
then
    show_error "Failed to create status script"
fi

if ! chmod +x status.sh; then
    show_error "Failed to make status script executable"
fi
show_success "Status script created"

echo -e "\n${GREEN}=== Setup Successfully Completed! ===${NC}"
echo -e "\nAccess your dashboard at:"
echo -e "${BLUE}http://$IP_ADDRESS:3000${NC}"
echo -e "\nLogin with:"
echo -e "Username: ${GREEN}koalbymqp${NC}"
echo -e "Password: ${GREEN}finley1234${NC}"
echo -e "\n${YELLOW}Important:${NC}"
echo "1. Run './status.sh' to check system status if needed"
echo "2. Use 'docker-compose logs' to view detailed logs if needed"