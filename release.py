import os
import re
import json
import shutil
from distutils.command.build_ext import build_ext
from multiprocessing import cpu_count
from pathlib import Path
from loguru import logger
from Cython.Build import cythonize
from setuptools import find_packages, Extension, setup


if os.path.exists("./build"):
    logger.debug("found exist build directory,remove it")

    shutil.rmtree("./build")

config_entity = None
if os.path.exists("./bin_maker.json"):
    logger.debug("found bin_maker.json,load extra config")

    with open("./bin_maker.json", "r", encoding="utf-8") as file:
        config_entity = json.load(file)

local_packages = find_packages()
new_local_packages = []

if config_entity is not None:
    if len(config_entity["exclude_modules"]) > 0:
        exclude_modules = []
        for m in local_packages:
            for modules in config_entity["exclude_modules"]:
                if m == modules or m.startswith(f"{modules}."):
                    logger.info(f"excluting modules:{m}")
                    if m not in exclude_modules:
                        exclude_modules.append(m)
        for m in local_packages:
            if m not in exclude_modules:
                new_local_packages.append(m)
    else:
        new_local_packages = local_packages

local_packages = new_local_packages
extensions = []


for obj in local_packages:
    dir_path = os.path.join(".", obj.replace(".", "/"))
    for name in os.listdir(dir_path):
        if not name.endswith(".py"):
            continue
        file_path = f"{dir_path}/{name}"
        if "__" in name or os.path.isdir(file_path):
            logger.debug(f"skip path:{file_path}")
            continue

        if (
            config_entity is not None
            and len(
                list(
                    filter(
                        lambda x: re.match(x, file_path), config_entity["exclude_files"]
                    )
                )
            )
            > 0
        ):
            logger.debug(f"skip path:{file_path}")
            continue

        extensions.append(
            Extension(
                obj + "." + name.replace(".py", ""),
                ["%s/%s" % (obj.replace(".", "/"), name)],
            )
        )


class KitBuildExt(build_ext):
    def run(self):
        build_ext.run(self)

        build_dir = Path(self.build_lib)
        root_dir = Path(__file__).parent

        target_dir = build_dir if not self.inplace else root_dir

        """
        copy __init__.py to cython compile path,otherwise compile will fail
        """
        for obj in local_packages:
            dir_path = obj.replace(".", "/")
            self.copy_file(Path(dir_path) / "__init__.py", os.getcwd(), target_dir)

    def copy_file(self, path, source_dir, destination_dir):
        if not (source_dir / path).exists():
            return

        shutil.copyfile(str(source_dir / path), str(destination_dir / path))


def build():
    global extensions
    if config_entity["only_files"]:
        _extensions = []
        for e in extensions:
            if e.sources[0] in config_entity["only_files"]:
                _extensions.append(e)
        extensions = _extensions
    logger.info(extensions)
    setup(
        name="bin-maker",
        version="2.0.0",
        packages=local_packages,
        platforms="any",
        ext_modules=cythonize(
            extensions,
            build_dir="build",
            annotate=True,
            compiler_directives=dict(always_allow_keywords=True),
            language_level=3,
        ),
        cmdclass=dict(build_ext=KitBuildExt),
    )


if __name__ == "__main__":
    build()
