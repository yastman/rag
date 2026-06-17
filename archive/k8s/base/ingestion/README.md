# Ingestion

## Purpose

Kubernetes ingestion workload for the Google Drive document pipeline.

## Data Contract

`deployment.yaml` mounts `drive-sync-pvc` at `/data/drive-sync` as read-only.
That PVC must be pre-populated before scaling the ingestion deployment above
zero replicas.

The expected producer is an external rclone sync process or storage provisioner
that mirrors Google Drive content into the `drive-sync-pvc` volume. The base
manifest declares the PVC so overlays render consistently, but it does not copy
or sync data into the volume by itself.

If the PVC is empty, ingestion can start successfully but process zero files.
Verify the mounted volume contains supported documents before running ingestion.

## Contents

- `deployment.yaml` — ingestion Deployment consuming `/data/drive-sync`
- `pvc.yaml` — externally-provisioned Google Drive sync mirror PVC

## Parent

- [..](..)
