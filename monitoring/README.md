# Monitoring Project for Raspberry Pi 5

## Overview
This project sets up a comprehensive monitoring system for your Raspberry Pi 5 using Docker containers. It includes Grafana and Node Exporter for visualizing system metrics, Prometheus for metrics collection.

## Prerequisites
- A Raspberry Pi 5 running a compatible Linux distribution.
- At least 1GB of free disk space.
- An active internet connection.
- The system must be recognized as a Raspberry Pi 

## Setup Instructions
1. Clone or copy the project repository to your Raspberry Pi.
2. Run the setup script with root privileges:

   sudo ./setup.sh

   The setup script performs the following tasks:
   - Validates that all required configuration files are present:
     - `compose.yaml`
     - `grafana/dashboards/dashboard.json`
     - `grafana/dashboards/dashboard.yaml`
     - `grafana/datasources/datasource.yaml`
     - `prometheus/prometheus.yaml`
   - Checks for a valid internet connection, sufficient disk space, and required port availability (ports 3000 for Grafana, 9090 for Prometheus, and 9100 for Node Exporter).
   - Installs Docker and Docker Compose if they are not already installed.
   - Configures and starts Docker, adding the current user to the Docker group.
   - Cleans up any existing Docker containers related to this project.
   - Launches monitoring services using Docker Compose.
   - Verifies that Grafana, Prometheus, and Node Exporter are running properly.
   - Creates a `status.sh` script to easily check the status of the containers and view logs.

## Accessing the Monitoring Dashboard
- Once the setup completes successfully, access Grafana by navigating to:

  http://<Raspberry_Pi_IP>:3000

- Login credentials (as provided by the setup script) are. You can of course change it as you wish in compose.yaml:
  - **Username:** koalbymqp
  - **Password:** finley1234

- Make sure to first access it from the Raspberry Pi browser first and login to make sure everything is working. Only when you confirmed that everything is working as intended, you can go ahead and access it from another device on the same network with the IP given by the setup script.

- Once logged in, go to Dashboards in the left sidebar and select Node Exporter. You can customize the dashboard and other settings as needed.

## Post-Setup Commands
- To check the status of the monitoring containers, run:

  ./status.sh

- To view detailed logs for troubleshooting:

  docker-compose logs

## Troubleshooting Tips
- Ensure that you run the setup script with sudo.
- If a required port is in use, the script will attempt to stop the container using it.
- Verify that your Raspberry Pi has an active internet connection.
- Check for sufficient disk space (minimum 1GB free) before running the script.
- Review the error messages displayed during the setup process for guidance on resolving issues.
- If containers do not start, inspect logs using docker-compose logs <service>.

## Additional Notes
- The setup script is designed specifically for a plug and play setup so please report if you encounter any issues.
- You can customize Docker Compose configurations, Grafana dashboards, and Prometheus settings as needed for your specific monitoring requirements.
