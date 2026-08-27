# Base image for every sandboxed task run: Python + Node + the 5 CLI harnesses
# under test. Built once, reused across runs via sandbox.py's `docker run`.
#
# ponytail: 5 CLI harness install layers verified <- container build passes -> live run verification of JSON schemas for all 5 CLIs inside container
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    jq \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Ubuntu 24.04's apt nodejs is 18.x -- too old for pi-coding-agent (needs >=20
# for the /v regex flag). NodeSource gives us 22.x instead.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --break-system-packages pytest

# CLI harnesses that install cleanly as root via a package manager.
RUN npm install -g @anthropic-ai/claude-code
RUN npm install -g @openai/codex
# Same package the host runs (@earendil-works fork, not the original
# @mariozechner one) -- benchmarking a different pi than the host uses would
# measure the wrong harness.
RUN npm install -g @earendil-works/pi-coding-agent

# Claude Code refuses --dangerously-skip-permissions as root ("cannot be used
# with root/sudo privileges") -- every harness in this system needs unattended
# auto-approval, so the container runs as a non-root user from here on.
# ubuntu:24.04 ships a uid-1000 "ubuntu" user already, which conveniently
# matches the common single-user host this was built against; sandbox.py
# mounts host credential dirs at this user's $HOME.
USER ubuntu
ENV HOME=/home/ubuntu

# opencode and antigravity install per-user (into $HOME), not system-wide --
# installing them as `ubuntu` here means their binaries land somewhere ubuntu
# can actually read/execute, unlike a root-owned /root/... a non-root user
# can't reach.
RUN curl -fsSL https://opencode.ai/install | bash
RUN curl -fsSL https://antigravity.google/cli/install.sh | bash

ENV PATH="/home/ubuntu/.local/bin:/home/ubuntu/.opencode/bin:${PATH}"

WORKDIR /workspace
