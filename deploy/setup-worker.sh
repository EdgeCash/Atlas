#!/usr/bin/env bash
# Set up the favorites worker (atlas/polymarket/worker.py) on a fresh Ubuntu server.
#
#   curl -fsSL https://raw.githubusercontent.com/EdgeCash/Atlas/main/deploy/setup-worker.sh | sudo bash
#   sudo nano /etc/atlas/favorites-worker.env              # fill in the secrets
#   sudo bash /srv/atlas/deploy/setup-worker.sh start      # one test tick, then the service
#   sudo bash /srv/atlas/deploy/setup-worker.sh update     # later: new code, restarted
#
# Safe to run again: each step skips what is already done. The install asks for
# one thing by hand - a deploy key added on GitHub - and waits until it works.

set -euo pipefail

REPO="${ATLAS_REPO:-git@github.com:EdgeCash/Atlas.git}"
BRANCH="${ATLAS_BRANCH:-main}"
DIR="${ATLAS_DIR:-/srv/atlas}"
ENV_FILE=/etc/atlas/favorites-worker.env
UNIT=/etc/systemd/system/favorites-worker.service
SERVICE=favorites-worker
NAME=atlas
KEY="/home/$NAME/.ssh/id_ed25519"
SELF="$DIR/deploy/setup-worker.sh"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }
as_atlas() { sudo -u "$NAME" -H "$@"; }

[ "$(id -u)" -eq 0 ] || die "run it as root: sudo bash $0 ${1:-}"

install() {
  say "Packages"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git python3-venv python3-pip ca-certificates openssh-client >/dev/null

  say "The $NAME user"
  id "$NAME" >/dev/null 2>&1 || useradd -m -s /bin/bash "$NAME"
  mkdir -p "$DIR" /etc/atlas
  chown "$NAME:$NAME" "$DIR"

  say "The deploy key"
  if [ ! -f "$KEY" ]; then
    as_atlas mkdir -p -m 700 "/home/$NAME/.ssh"
    as_atlas ssh-keygen -q -t ed25519 -N "" -C "atlas-worker@$(hostname)" -f "$KEY"
  fi
  as_atlas bash -c 'ssh-keyscan -t ed25519 github.com 2>/dev/null >> ~/.ssh/known_hosts && sort -u -o ~/.ssh/known_hosts ~/.ssh/known_hosts' \
    || echo "warning: could not read GitHub's SSH host key; is outbound port 22 open on this server?"
  tried=""
  until err=$(as_atlas git ls-remote "$REPO" HEAD 2>&1 >/dev/null); do
    [ -z "$tried" ] || printf '\nGitHub still refuses the key: %s\n' "${err##*$'\n'}"
    tried=1
    echo
    echo "Add this key on GitHub: the Atlas repository -> Settings -> Deploy keys -> Add deploy key."
    echo "Give it any title, paste the line below, and tick \"Allow write access\":"
    echo
    cat "$KEY.pub"
    echo
    read -r -p "Press Enter once it is added... " _ </dev/tty
  done

  say "The code ($BRANCH)"
  if [ ! -d "$DIR/.git" ]; then
    as_atlas git clone -q --branch "$BRANCH" "$REPO" "$DIR"
  else
    as_atlas git -C "$DIR" pull -q --ff-only origin "$BRANCH"
  fi
  [ -f "$DIR/atlas/polymarket/worker.py" ] \
    || die "the $BRANCH branch has no worker yet. Merge the pull request that adds atlas/polymarket/worker.py, then run this again."
  as_atlas git -C "$DIR" push -q --dry-run origin "HEAD:$BRANCH" >/dev/null 2>&1 \
    || die "the deploy key can read but not push. Tick \"Allow write access\" on it in GitHub, then run this again."

  say "Python"
  [ -x "$DIR/.venv/bin/python" ] || as_atlas python3 -m venv "$DIR/.venv"
  as_atlas "$DIR/.venv/bin/pip" install -q --upgrade pip
  as_atlas "$DIR/.venv/bin/pip" install -q -e "$DIR"

  say "The environment file"
  [ -f "$ENV_FILE" ] || cp "$DIR/deploy/favorites-worker.env.example" "$ENV_FILE"
  chown "root:$NAME" "$ENV_FILE"
  chmod 640 "$ENV_FILE"

  say "The service (not started yet)"
  cp "$DIR/deploy/favorites-worker.service" "$UNIT"
  systemctl daemon-reload

  cat <<EOF

Installed. Two steps left:

  1. Fill in the secrets (Ctrl+O, Enter, Ctrl+X saves and leaves):
       sudo nano $ENV_FILE

  2. Test one tick and start the service:
       sudo bash $SELF start
EOF
}

start() {
  [ -f "$ENV_FILE" ] && [ -f "$UNIT" ] || die "install first: curl -fsSL https://raw.githubusercontent.com/EdgeCash/Atlas/main/deploy/setup-worker.sh | sudo bash"
  grep -Eq '^ATLAS_OWNER_KEY=.+' "$ENV_FILE" \
    || echo "note: ATLAS_OWNER_KEY is empty, so positions are taken but nothing is ordered or sealed."

  say "One tick, nothing pushed"
  # A transient unit reads the environment file exactly as the service will.
  systemd-run --quiet --wait --pipe --collect --uid="$NAME" --gid="$NAME" -p WorkingDirectory="$DIR" \
    -p EnvironmentFile="$ENV_FILE" "$DIR/.venv/bin/python" -m atlas.polymarket.worker --once --no-push \
    || die "the test tick failed; the lines above say why."

  say "Starting the service"
  systemctl enable --now "$SERVICE"
  sleep 3
  systemctl is-active --quiet "$SERVICE" || die "the service did not stay up: journalctl -u $SERVICE -n 50"
  cat <<EOF

Running. It survives reboots and restarts itself after a crash.

  Watch it:          journalctl -u $SERVICE -f
  Stop it:           sudo systemctl stop $SERVICE
  New code later:    sudo bash $SELF update

Last step, on GitHub: Settings -> Secrets and variables -> Actions -> Variables,
add FAVORITES_TAKER with the value worker, so the scheduled runs stop taking
the rule's positions themselves.
EOF
}

update() {
  [ -d "$DIR/.git" ] || die "install first."
  say "Stopping the worker"
  systemctl stop "$SERVICE" 2>/dev/null || true
  say "New code"
  as_atlas git -C "$DIR" fetch -q origin "$BRANCH"
  # The code only. The record and the ledger stay as this server holds them: the worker lays them over the
  # branch's copies row by row on its first tick, which git's own merge cannot be trusted to do.
  as_atlas git -C "$DIR" checkout -q "origin/$BRANCH" -- . ':(exclude)tracking'
  as_atlas "$DIR/.venv/bin/pip" install -q -e "$DIR"
  cp "$DIR/deploy/favorites-worker.service" "$UNIT"
  systemctl daemon-reload
  systemctl start "$SERVICE"
  sleep 3
  systemctl is-active --quiet "$SERVICE" || die "the service did not stay up: journalctl -u $SERVICE -n 50"
  say "Running: $(as_atlas git -C "$DIR" log --oneline -1 "origin/$BRANCH")"
}

case "${1:-install}" in
  install) install ;;
  start) start ;;
  update) update ;;
  *) die "usage: sudo bash $SELF [install|start|update]" ;;
esac
