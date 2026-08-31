"""
Submits a K8s Job for each loop run so every session gets an isolated pod.
Only used when LOOP_EXECUTOR=k8s (set in prod). Local dev still uses asyncio tasks.
"""
import os
import uuid
from kubernetes import client, config  # pip: kubernetes

def _load_config():
    if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token"):
        config.load_incluster_config()   # running inside a pod
    else:
        config.load_kube_config()        # local kubectl context


def submit_loop_job(session_id: str, task_id: str, repo_path: str, model: str, max_iterations: int) -> str:
    _load_config()
    batch = client.BatchV1Api()

    job_name = f"loop-{session_id[:8]}-{uuid.uuid4().hex[:6]}"
    namespace = os.getenv("K8S_NAMESPACE", "loop-runner")

    job = client.V1Job(
        metadata=client.V1ObjectMeta(
            name=job_name,
            namespace=namespace,
            labels={"app": "loop-worker", "session-id": session_id},
        ),
        spec=client.V1JobSpec(
            ttl_seconds_after_finished=600,
            backoff_limit=0,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": "loop-worker"}),
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    service_account_name="loop-runner-sa",
                    containers=[
                        client.V1Container(
                            name="loop-worker",
                            image=os.getenv("WORKER_IMAGE", "ghcr.io/YOUR_ORG/loop-runner-backend:latest"),
                            command=["python", "-m", "backend.core.loop_worker"],
                            env=[
                                client.V1EnvVar(name="SESSION_ID", value=session_id),
                                client.V1EnvVar(name="TASK_ID", value=task_id),
                                client.V1EnvVar(name="REPO_PATH", value=repo_path),
                                client.V1EnvVar(name="MODEL", value=model),
                                client.V1EnvVar(name="MAX_ITERATIONS", value=str(max_iterations)),
                            ],
                            env_from=[
                                client.V1EnvFromSource(config_map_ref=client.V1ConfigMapEnvSource(name="loop-runner-config")),
                                client.V1EnvFromSource(secret_ref=client.V1SecretEnvSource(name="loop-runner-secrets")),
                            ],
                            resources=client.V1ResourceRequirements(
                                requests={"memory": "512Mi", "cpu": "500m"},
                                limits={"memory": "2Gi", "cpu": "2000m"},
                            ),
                            volume_mounts=[client.V1VolumeMount(name="repos", mount_path="/repos")],
                        )
                    ],
                    volumes=[
                        client.V1Volume(
                            name="repos",
                            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name="shared-repos-pvc"),
                        )
                    ],
                ),
            ),
        ),
    )

    batch.create_namespaced_job(namespace=namespace, body=job)
    return job_name


def delete_loop_job(job_name: str):
    _load_config()
    batch = client.BatchV1Api()
    namespace = os.getenv("K8S_NAMESPACE", "loop-runner")
    batch.delete_namespaced_job(name=job_name, namespace=namespace, body=client.V1DeleteOptions(propagation_policy="Foreground"))
