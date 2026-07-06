#!/bin/bash
# Generate TypeScript types from the backend OpenAPI schema
# Run from the project root

set -e

BACKEND_DIR="./backend"
FRONTEND_DIR="./frontend"
OPENAPI_FILE="/tmp/openapi.json"

echo "Generating OpenAPI schema from backend..."
cd "$BACKEND_DIR"
python3 -c "
import sys
sys.path.insert(0, '.')
import os
os.environ['JWT_SECRET'] = 'development-secret-key-for-type-gen-only'
os.environ['DEBUG'] = 'true'
from main import app
import json
with open('$OPENAPI_FILE', 'w') as f:
    json.dump(app.openapi(), f, indent=2)
" 2>/dev/null || {
    echo "Warning: Could not generate OpenAPI schema. Is the backend setup correctly?"
    echo "Falling back: generating a basic API client stub..."
    cat > "$FRONTEND_DIR/src/api.gen.ts" << 'EOF'
// Auto-generated API client stub
// Run scripts/gen-types.sh with a running backend to generate full types
export const API_BASE = '/api';
EOF
    exit 0
}

echo "Generating TypeScript types..."
cd "$FRONTEND_DIR"

if command -v npx &> /dev/null; then
    npx --yes openapi-typescript "$OPENAPI_FILE" --output src/types/api.gen.ts 2>/dev/null || {
        echo "openapi-typescript not available. Installing..."
        npm install --save-dev openapi-typescript
        npx openapi-typescript "$OPENAPI_FILE" --output src/types/api.gen.ts
    }
    echo "Generated src/types/api.gen.ts"
else
    echo "npx not found. Install Node.js to generate types."
fi

echo "Done!"
