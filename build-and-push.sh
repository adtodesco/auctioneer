#!/bin/bash
set -e

# Build and push Docker images with both version tag and latest tag
# Usage: ./build-and-push.sh [version]
# If no version is provided, uses git commit hash

# Determine version tag
if [ -z "$1" ]; then
    VERSION=$(git rev-parse --short HEAD)
    echo "No version provided, using git commit hash: $VERSION"
else
    VERSION=$1
    echo "Using provided version: $VERSION"
fi

# Image names (update these if your registry/username changes)
WEB_IMAGE="ghcr.io/adtodesco/auctioneer"
NGINX_IMAGE="ghcr.io/adtodesco/auctioneer-nginx"

echo ""
echo "=== Building images with docker-compose ==="
docker-compose build

echo ""
echo "=== Tagging images ==="
echo "Web image: $WEB_IMAGE:latest -> $WEB_IMAGE:$VERSION"
docker tag $WEB_IMAGE:latest $WEB_IMAGE:$VERSION

echo "Nginx image: $NGINX_IMAGE:latest -> $NGINX_IMAGE:$VERSION"
docker tag $NGINX_IMAGE:latest $NGINX_IMAGE:$VERSION

echo ""
echo "=== Pushing version tags ==="
docker push $WEB_IMAGE:$VERSION
docker push $NGINX_IMAGE:$VERSION

echo ""
echo "=== Pushing latest tags ==="
docker push $WEB_IMAGE:latest
docker push $NGINX_IMAGE:latest

echo ""
echo "✅ Successfully pushed images with tags:"
echo "   - $WEB_IMAGE:$VERSION"
echo "   - $WEB_IMAGE:latest"
echo "   - $NGINX_IMAGE:$VERSION"
echo "   - $NGINX_IMAGE:latest"
echo ""
echo "To deploy on VM, run:"
echo "   docker compose pull && docker compose up -d"
