#!/bin/bash
# Create the newsdock Kafka topics. Safe to run repeatedly (--if-not-exists).
# One partition and replication factor 1: single broker, ordering over throughput (M1 design).
set -euo pipefail
BOOTSTRAP="${KAFKA_BOOTSTRAP_SERVERS_INTERNAL:-kafka:9092}"
for topic in gkg.raw gkg.clean gkg.dlq; do
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server "$BOOTSTRAP" \
    --create --if-not-exists --topic "$topic" --partitions 1 --replication-factor 1
done
