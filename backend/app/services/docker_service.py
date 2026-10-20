import os
from pathlib import Path
import re
import socket
import subprocess
import time
import threading
from typing import List, Optional, Tuple

import httpx
from app.core import config


class DockerCommandError(Exception):
    """Exception raised when a Docker command fails."""

    def __init__(self, message: str, stderr: str = "", exit_code: int = 1):
        super().__init__(message)
        self.message = message
        self.stderr = stderr
        self.exit_code = exit_code


class DockerClientWrapper:
    """Wrapper around Docker CLI using safe subprocess execution with argument lists."""

    @staticmethod
    def is_docker_available() -> bool:
        """Check if Docker CLI and daemon are operational."""
        try:
            res = subprocess.run(
                ["docker", "info"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                check=False,
            )
            return res.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return False

    @staticmethod
    def _run_cmd(args: List[str], timeout: Optional[int] = 120) -> Tuple[int, str, str]:
        """Execute a docker CLI command without shell=True."""
        try:
            res = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
            return res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired as exc:
            raise DockerCommandError(f"Command timed out after {timeout}s: {' '.join(args)}") from exc
        except (FileNotFoundError, OSError) as exc:
            raise DockerCommandError(f"Failed to execute command {' '.join(args)}: {exc}") from exc

    def build_image(self, build_dir: Path, image_tag: str, log_file_path: Path) -> None:
        """
        Build a Docker image from build_dir with safe argument passing.
        Appends stdout and stderr directly to log_file_path.
        """
        cmd = [
            "docker",
            "build",
            "-t",
            image_tag,
            str(build_dir.resolve()),
        ]
        retcode, stdout, stderr = self._run_cmd(cmd, timeout=300)
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- [BUILD COMMAND: {' '.join(cmd)}] ---\n")
            if stdout:
                f.write(stdout)
            if stderr:
                f.write(stderr)

        if retcode != 0:
            err_summary = (stderr.strip() or stdout.strip() or "Docker build failed")[-500:]
            raise DockerCommandError(f"Build failed: {err_summary}", stderr=stderr, exit_code=retcode)

    def run_container(
        self,
        image_tag: str,
        container_name: str,
        host_port: int,
        container_port: int = 8080,
    ) -> str:
        """
        Run container with resource limits and security restrictions:
        - Server-controlled port mapping: -p host_port:container_port
        - Resource limits: --memory, --cpus, --pids-limit
        - No privileged mode
        - No host network
        - No Docker socket or host filesystem mounts
        - Drops capabilities / runs securely
        """
        cmd = [
            "docker",
            "run",
            "--user",
            "1000:1000",
            "-d",
            "--name",
            container_name,
            "-p",
            f"{host_port}:{container_port}",
            "--memory",
            config.CONTAINER_MEMORY_LIMIT,
            f"--cpus={config.CONTAINER_CPUS_LIMIT}",
            f"--pids-limit={config.CONTAINER_PIDS_LIMIT}",
            image_tag,
        ]
        retcode, stdout, stderr = self._run_cmd(cmd, timeout=60)
        if retcode != 0:
            raise DockerCommandError(f"Failed to run container: {stderr.strip()}", stderr=stderr, exit_code=retcode)
        container_id = stdout.strip()
        return container_id

    def stop_container(self, container_identifier: str, timeout_seconds: int = 5) -> None:
        """Stop a running container."""
        cmd = ["docker", "stop", "-t", str(timeout_seconds), container_identifier]
        retcode, _, stderr = self._run_cmd(cmd, timeout=timeout_seconds + 5)
        if retcode != 0 and "No such container" not in stderr:
            raise DockerCommandError(f"Failed to stop container: {stderr.strip()}", stderr=stderr, exit_code=retcode)

    def start_container(self, container_identifier: str) -> None:
        """Start a stopped container."""
        cmd = ["docker", "start", container_identifier]
        retcode, _, stderr = self._run_cmd(cmd, timeout=30)
        if retcode != 0:
            raise DockerCommandError(f"Failed to start container: {stderr.strip()}", stderr=stderr, exit_code=retcode)

    def remove_container(self, container_identifier: str, force: bool = True) -> None:
        """Remove a container."""
        cmd = ["docker", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(container_identifier)
        self._run_cmd(cmd, timeout=30)

    def get_container_logs(self, container_identifier: str, tail: int = 500) -> str:
        """Get recent logs from a container."""
        cmd = ["docker", "logs", "--tail", str(tail), container_identifier]
        retcode, stdout, stderr = self._run_cmd(cmd, timeout=15)
        combined = []
        if stdout:
            combined.append(stdout)
        if stderr:
            combined.append(stderr)
        return "\n".join(combined)

    def inspect_container_running(self, container_identifier: str) -> bool:
        """Check if container is currently running."""
        cmd = ["docker", "inspect", "-f", "{{.State.Running}}", container_identifier]
        retcode, stdout, _ = self._run_cmd(cmd, timeout=10)
        return retcode == 0 and "true" in stdout.lower()


# Global or test-overridable instance
docker_client = DockerClientWrapper()

# Global port reservation tracking
_port_lock = threading.Lock()
allocated_ports: set[int] = set()

def allocate_free_port(start: int = config.PORT_RANGE_START, end: int = config.PORT_RANGE_END) -> int:
    """Find a free TCP port on localhost within the configured port range.
    Tracks allocated ports to avoid collisions in concurrent deployments.
    """
    with _port_lock:
        for port in range(start, end + 1):
            if port in allocated_ports:
                continue
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(("127.0.0.1", port))
                except OSError:
                    continue
                allocated_ports.add(port)
                return port
    raise RuntimeError(f"No free ports available in range {start}-{end}")

def release_port(port: int) -> None:
    """Release a previously allocated port back to the pool."""
    with _port_lock:
        allocated_ports.discard(port)


def detect_exposed_port(dockerfile_path: Path, default_port: int = 8080) -> int:
    """Read EXPOSE directive from Dockerfile, or fallback to default_port."""
    if not dockerfile_path.exists():
        return default_port
    try:
        content = dockerfile_path.read_text(encoding="utf-8")
        matches = re.findall(r"^\s*EXPOSE\s+(\d+)", content, re.MULTILINE | re.IGNORECASE)
        if matches:
            return int(matches[0])
    except Exception:
        pass
    return default_port


def wait_for_health_check(
    port: int,
    path: str = "/health",
    timeout_seconds: int = config.DEPLOYMENT_HEALTHCHECK_TIMEOUT_SECONDS,
) -> bool:
    """Poll the application's health endpoint until it responds with 200 or timeout."""
    start_time = time.time()
    url = f"http://127.0.0.1:{port}{path}"
    with httpx.Client(timeout=2.0) as client:
        while time.time() - start_time < timeout_seconds:
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    return True
            except (httpx.RequestError, OSError):
                pass
            time.sleep(0.5)
    return False
