import os
from typing import List

from ci.ray_ci.container import Container, _DOCKER_ECR_REPO
from ci.ray_ci.builder_container import PYTHON_VERSIONS
from ci.ray_ci.utils import docker_pull, POSTMERGE_PIPELINE

PLATFORM = ["cu118"]

GPU_PLATFORM = "cu118"


class DockerContainer(Container):
    def __init__(self, python_version: str, platform: str, image_type: str) -> None:
        super().__init__(
            "forge",
            volumes=[
                f"{os.environ['RAYCI_CHECKOUT_DIR']}:/rayci",
                "/var/run/docker.sock:/var/run/docker.sock",
            ],
        )
        self.python_version = python_version
        self.platform = platform
        self.image_type = image_type

    def run(self) -> None:
        base_image = (
            f"{_DOCKER_ECR_REPO}:{os.environ['RAYCI_BUILD_ID']}"
            f"-{self.image_type}{self.python_version}{self.platform}base"
        )
        docker_pull(base_image)
        wheel_name = (
            "ray-3.0.0.dev0-"
            f"{PYTHON_VERSIONS[self.python_version]['bin_path']}-"
            "manylinux2014_x86_64.whl"
        )
        constraints_file = (
            "requirements_compiled_py37.txt"
            if self.python_version == "py37"
            else "requirements_compiled.txt"
        )
        ray_images = self._get_image_names()
        ray_image = ray_images[0]
        cmds = [
            "./ci/build/build-ray-docker.sh "
            f"{wheel_name} {base_image} {constraints_file} {ray_image}"
        ]
        if self._should_upload_docker():
            cmds += [
                "pip install -q aws_requests_auth boto3",
                "python .buildkite/copy_files.py --destination docker_login",
            ]
            for alias in self._get_image_names():
                cmds += [
                    f"docker tag {ray_image} {alias}",
                    f"docker push {alias}",
                ]
        self.run_script(cmds)

    def _should_upload_docker(self) -> bool:
        return os.environ["BUILDKITE_PIPELINE_ID"] == POSTMERGE_PIPELINE

    def _get_image_names(self) -> List[str]:
        # Image name is composed by ray version tag, python version and platform.
        # See https://docs.ray.io/en/latest/ray-overview/installation.html for
        # more information on the image tags.
        versions = [f"{os.environ['BUILDKITE_COMMIT'][:6]}"]
        if os.environ["BUILDKITE_BRANCH"] == "master":
            # TODO(can): add ray version if this is a release branch
            versions.append("nightly")

        platforms = [f"-{self.platform}"]
        if self.platform == "cpu" and self.image_type == "ray":
            # no tag is alias to cpu for ray image
            platforms.append("")
        elif self.platform == GPU_PLATFORM:
            # gpu is alias to cu118 for ray image
            platforms.append("-gpu")
            if self.image_type == "ray-ml":
                # no tag is alias to gpu for ray-ml image
                platforms.append("")

        alias_images = []
        ray_repo = f"rayproject/{self.image_type}"
        for version in versions:
            for platform in platforms:
                alias = f"{ray_repo}:{version}-{self.python_version}{platform}"
                alias_images.append(alias)

        return alias_images
