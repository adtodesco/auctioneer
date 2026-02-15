#!/bin/bash
set -e

# Deployment script for VM
# This script pulls the latest images and restarts services

echo "=== Stopping services ==="
docker-compose down

echo ""
echo "=== Removing old images to force fresh pull ==="
# Get image names from docker-compose.yml and remove them
IMAGES=$(docker-compose config | grep 'image:' | awk '{print $2}')
for IMAGE in $IMAGES; do
    echo "Removing $IMAGE"
    docker rmi $IMAGE 2>/dev/null || echo "  (image not found locally, skipping)"
done

echo ""
echo "=== Pulling latest images ==="
docker-compose pull --no-cache

echo ""
echo "=== Starting services ==="
docker-compose up -d

echo ""
echo "=== Waiting for services to start ==="
sleep 3

echo ""
echo "=== Service status ==="
docker-compose ps

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Useful commands:"
echo "  View logs:        docker-compose logs -f"
echo "  Restart services: docker-compose restart"
echo "  Init database:    docker exec -it auctioneer-web-1 flask init-db"
echo "  Flask shell:      docker exec -it auctioneer-web-1 flask shell"
