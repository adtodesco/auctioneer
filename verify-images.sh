#!/bin/bash
# Verify that VM is running the latest images from GHCR

set -e

echo "=== Checking current VM images ==="
echo ""

# Get running image IDs
WEB_IMAGE_ID=$(docker ps --filter "name=auctioneer-web" --format "{{.Image}}")
NGINX_IMAGE_ID=$(docker ps --filter "name=auctioneer-nginx" --format "{{.Image}}")

echo "Currently running:"
echo "  Web:   $WEB_IMAGE_ID"
echo "  Nginx: $NGINX_IMAGE_ID"
echo ""

# Check when images were created
echo "=== Image creation times ==="
docker images ghcr.io/adtodesco/auctioneer --format "table {{.Repository}}\t{{.Tag}}\t{{.CreatedAt}}\t{{.ID}}"
docker images ghcr.io/adtodesco/auctioneer-nginx --format "table {{.Repository}}\t{{.Tag}}\t{{.CreatedAt}}\t{{.ID}}"
echo ""

# Try pulling latest to see if there's an update
echo "=== Checking for updates ==="
echo "Pulling latest images from GHCR..."
docker pull ghcr.io/adtodesco/auctioneer:latest
docker pull ghcr.io/adtodesco/auctioneer-nginx:latest
echo ""

# Check again after pull
NEW_WEB_IMAGE_ID=$(docker images ghcr.io/adtodesco/auctioneer:latest --format "{{.ID}}")
NEW_NGINX_IMAGE_ID=$(docker images ghcr.io/adtodesco/auctioneer-nginx:latest --format "{{.ID}}")

# Get running container image IDs
RUNNING_WEB_ID=$(docker ps --filter "name=auctioneer-web" --format "{{.ImageID}}")
RUNNING_NGINX_ID=$(docker ps --filter "name=auctioneer-nginx" --format "{{.ImageID}}")

echo "=== Verification Results ==="
if [ "$NEW_WEB_IMAGE_ID" = "$RUNNING_WEB_ID" ]; then
    echo "✅ Web image is UP TO DATE"
else
    echo "⚠️  Web image NEEDS UPDATE (run: docker-compose up -d)"
    echo "   Running: $RUNNING_WEB_ID"
    echo "   Latest:  $NEW_WEB_IMAGE_ID"
fi

if [ "$NEW_NGINX_IMAGE_ID" = "$RUNNING_NGINX_ID" ]; then
    echo "✅ Nginx image is UP TO DATE"
else
    echo "⚠️  Nginx image NEEDS UPDATE (run: docker-compose up -d)"
    echo "   Running: $RUNNING_NGINX_ID"
    echo "   Latest:  $NEW_NGINX_IMAGE_ID"
fi
