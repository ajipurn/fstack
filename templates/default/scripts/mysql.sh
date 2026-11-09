#!/bin/sh
# Dev MySQL for `make db-up` / `make db-down`. The app connects as root
# (APP_DATABASE_URL) and `make seed` creates the project's database.
#
#   container  Apple's `container` CLI: one shared container (default `mysql`) serves
#              every project.
#   docker     docker compose (compose.yaml): one MySQL per project.
#
# DB_RUNTIME picks one; empty = whichever is running, Apple container first.
# DB_CONTAINER, DB_IMAGE, DB_PORT and DB_ROOT_PASSWORD (default `root`) only apply
# when the Apple container is created for the first time.
set -eu

action=${1:-up}
name=${DB_CONTAINER:-mysql}
image=${DB_IMAGE:-mysql:8.4}
port=${DB_PORT:-3306}

apple_running() {
  container system status 2>/dev/null | grep -Eq '^status +running'
}

detect() {
  if command -v container >/dev/null 2>&1 && apple_running; then echo container
  elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then echo docker
  elif command -v container >/dev/null 2>&1; then echo container
  else echo docker
  fi
}

container_up() {
  if ! apple_running; then
    echo "starting Apple container services"
    container system start
  fi
  if ! container inspect "$name" >/dev/null 2>&1; then
    container volume inspect "${name}_data" >/dev/null 2>&1 \
      || container volume create "${name}_data" >/dev/null
    echo "creating $name ($image) on 127.0.0.1:$port"
    container run -d --progress none --name "$name" -p "127.0.0.1:$port:3306" \
      -v "${name}_data:/var/lib/mysql" -e MYSQL_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-root}" \
      "$image" --character-set-server=utf8mb4 --collation-server=utf8mb4_bin >/dev/null
  elif ! container ls -q | grep -qx "$name"; then
    container start "$name" >/dev/null
  fi
  # mysqladmin ping exits 0 once the server accepts TCP, even on "access denied";
  # the first-boot init server listens on a socket only, so this waits it out.
  printf 'mysql (container %s) ' "$name"
  i=0
  until container exec "$name" mysqladmin ping -h 127.0.0.1 --silent >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 120 ]; then
      echo "not ready after 120s (container logs $name)"
      exit 1
    fi
    printf .
    sleep 1
  done
  echo " ready"
}

container_down() {
  if container ls -q | grep -qx "$name"; then
    container stop "$name" >/dev/null
    echo "stopped container $name (shared: other projects using it are offline too)"
  else
    echo "container $name is not running"
  fi
}

runtime=${DB_RUNTIME:-$(detect)}
case "$runtime:$action" in
  container:up) container_up ;;
  container:down) container_down ;;
  docker:up) docker compose up -d --wait mysql ;;
  docker:down) docker compose down ;;
  *)
    echo "usage: DB_RUNTIME=container|docker $0 up|down" >&2
    exit 2
    ;;
esac
