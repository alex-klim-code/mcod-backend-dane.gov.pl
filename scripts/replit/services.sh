#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
service_root="$PWD/.cache/services"
mkdir -p "$service_root/redis" "$service_root/rabbitmq" "$service_root/elasticsearch-data" "$service_root/elasticsearch-logs"

cleanup() {
  kill "${redis_pid:-}" "${rabbit_pid:-}" "${elastic_pid:-}" 2>/dev/null || true
  wait || true
}
trap cleanup EXIT INT TERM

redis-server --bind 127.0.0.1 --dir "$service_root/redis" --appendonly yes &
redis_pid=$!
export RABBITMQ_MNESIA_BASE="$service_root/rabbitmq/mnesia"
export RABBITMQ_LOG_BASE="$service_root/rabbitmq/log"
export RABBITMQ_PID_FILE="$service_root/rabbitmq/rabbitmq.pid"
export RABBITMQ_NODE_IP_ADDRESS=127.0.0.1
export ERL_EPMD_ADDRESS=127.0.0.1
export RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS="+S 2:2 -kernel inet_dist_use_interface {127,0,0,1}"
rabbitmq-server &
rabbit_pid=$!

elastic="$service_root/elasticsearch-6.8.23"
for name in hunspell synonyms; do
  if [[ ! -e "$elastic/config/$name" ]]; then
    ln -s "$PWD/docker/elasticsearch/$name" "$elastic/config/$name"
  fi
done
cp docker/elasticsearch/stopwords.txt "$elastic/config/stopwords.txt"
export ES_JAVA_OPTS="-Xms256m -Xmx256m"
"$elastic/bin/elasticsearch" \
  -Ecluster.name=mcod-replit \
  -Enetwork.host=127.0.0.1 \
  -Ediscovery.type=single-node \
  -Escript.painless.regex.enabled=true \
  -Expack.ml.enabled=false \
  -Epath.data="$service_root/elasticsearch-data" \
  -Epath.logs="$service_root/elasticsearch-logs" &
elastic_pid=$!
wait -n "$redis_pid" "$rabbit_pid" "$elastic_pid"
