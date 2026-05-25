#!/usr/bin/env bash
# check-env.sh — Validate your .env before starting the stack.
# Usage: bash scripts/check-env.sh
# Run this before `docker compose up` to catch missing or default values.

set -euo pipefail

ENV_FILE="${1:-.env}"
ERRORS=0
WARNINGS=0

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

if [ ! -f "$ENV_FILE" ]; then
  echo -e "${RED}ERROR: $ENV_FILE not found.${NC}"
  echo "  Run: cp .env.example .env  then fill in all CHANGE_ME values."
  exit 1
fi

# Load the env file (ignore comments and blank lines)
while IFS='=' read -r key value; do
  [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
  key=$(echo "$key" | xargs)
  value=$(echo "$value" | xargs | sed 's/#.*//' | xargs)
  export "CHECK_${key}=${value}"
done < "$ENV_FILE"

check_required() {
  local var="$1"
  local envvar="CHECK_${var}"
  local val="${!envvar:-}"
  if [ -z "$val" ] || [[ "$val" == *"CHANGE_ME"* ]]; then
    echo -e "  ${RED}✗ MISSING${NC}  $var — must be set before deployment"
    ERRORS=$((ERRORS + 1))
  else
    echo -e "  ${GREEN}✓ OK${NC}       $var"
  fi
}

check_not_default() {
  local var="$1"
  local bad_value="$2"
  local envvar="CHECK_${var}"
  local val="${!envvar:-}"
  if [ "$val" = "$bad_value" ] || [ -z "$val" ]; then
    echo -e "  ${RED}✗ INSECURE${NC} $var — still set to default \"$bad_value\""
    ERRORS=$((ERRORS + 1))
  else
    echo -e "  ${GREEN}✓ OK${NC}       $var"
  fi
}

check_min_length() {
  local var="$1"
  local min="$2"
  local envvar="CHECK_${var}"
  local val="${!envvar:-}"
  if [ ${#val} -lt "$min" ]; then
    echo -e "  ${YELLOW}⚠ WEAK${NC}     $var — should be at least $min characters (got ${#val})"
    WARNINGS=$((WARNINGS + 1))
  else
    echo -e "  ${GREEN}✓ OK${NC}       $var (${#val} chars)"
  fi
}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  MKLanLocal — pre-flight environment check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "[ Security ]"
check_required      SESSION_SECRET
check_min_length    SESSION_SECRET 32
check_not_default   SESSION_SECRET "change-me"
check_not_default   SESSION_SECRET "CHANGE_ME_generate_with_openssl_rand_hex_32"

echo ""
echo "[ Credentials ]"
check_required      ADMIN_PASSWORD
check_not_default   ADMIN_PASSWORD "change-me"
check_not_default   ADMIN_PASSWORD "CHANGE_ME_admin_password"
check_min_length    ADMIN_PASSWORD 8

check_required      CURATOR_PASSWORD
check_not_default   CURATOR_PASSWORD "change-me"
check_not_default   CURATOR_PASSWORD "CHANGE_ME_curator_password"

check_required      GUEST_PASSWORD
check_not_default   GUEST_PASSWORD "change-me"
check_not_default   GUEST_PASSWORD "CHANGE_ME_guest_password"

echo ""
echo "[ Database ]"
check_required      POSTGRES_PASSWORD
check_not_default   POSTGRES_PASSWORD "change-me"
check_not_default   POSTGRES_PASSWORD "media_indexer"
check_not_default   POSTGRES_PASSWORD "CHANGE_ME_db_password"
check_required      DATABASE_URL

echo ""
echo "[ Networking ]"
check_required      FRONTEND_ORIGIN
check_required      INTERNAL_API_BASE_URL

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$ERRORS" -gt 0 ]; then
  echo -e "  ${RED}FAILED${NC} — $ERRORS error(s), $WARNINGS warning(s)"
  echo "  Fix the errors above before starting the stack."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  exit 1
elif [ "$WARNINGS" -gt 0 ]; then
  echo -e "  ${YELLOW}PASSED with warnings${NC} — $WARNINGS warning(s)"
  echo "  The stack will start, but consider addressing the warnings."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  exit 0
else
  echo -e "  ${GREEN}ALL CHECKS PASSED${NC}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  exit 0
fi
