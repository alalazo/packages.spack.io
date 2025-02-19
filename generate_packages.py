#!/usr/bin/env spack-python

# This script will generate package metadata files for
# each package in the latest version of spack
#
# Usage:
# spack python generate_packages.py


import json
import tempfile
import subprocess
import shutil
import sys
import os
from datetime import datetime

import spack.repo
import spack.spec
import spack.version

here = os.getcwd()

# spack python does not have __file__
__file__ = os.path.join(here, "generate_packages.py")
if not os.path.exists(__file__):
    sys.exit("Please run in the same directory as generate_packages.py")

## File Operations


def write_json(content, filename):
    with open(filename, "w") as outfile:
        outfile.write(json.dumps(content, indent=4))


def main():

    pkgs = spack.repo.all_package_names(include_virtuals=True)
    deps_of = {}
    descriptions = {}
    metas = {}
    package_variants = {}

    # Iterate through consistent order
    pkgs = set(sorted(pkgs))

    # Prepre to create repology output alongside packages files
    repology = {
        "repository_name": "spack",
        "num_packages": len(pkgs),
        "last_update": str(datetime.now()),
        "packages": {},
    }

    for i, package in enumerate(pkgs):

        print("Parsing %s, %s of %s" % (package, i, len(pkgs)))
        pkg_class = spack.repo.path.get_pkg_class(package)
        # this should be refactored later to just use the pkg_class
        pkg = pkg_class(spack.spec.Spec(package))
        descriptions[pkg.name] = pkg.format_doc().strip()

        patches = []
        patches_repology = []
        if pkg.patches:
            for key, patchlist in pkg.patches.items():
                for patch in patchlist:
                    patch = patch.to_dict()
                    patch.update({"version": str(key)})
                    patches.append(patch)
                    if patch["version"]:
                        patches_repology.append(
                            "%s when %s"
                            % (
                                patch.get("relative_path") or patch.get("url"),
                                patch["version"],
                            )
                        )
                    else:
                        patches_repology.append(
                            patch.get("relative_path") or patch.get("url")
                        )

        resources = []
        if pkg.resources:
            for version, resourcelist in pkg.resources.items():
                for resource in resourcelist:
                    resources.append(
                        {
                            "version": str(version),
                            "name": resource.name,
                            "destination": resource.destination,
                            "placement": resource.placement,
                        }
                    )

        # this will miss ibm-java, which only adds versions for ppc64le, but we can fix
        # that in the package later.
        if not pkg.versions:
            continue

        versions = []
        seen_versions = set()
        for version, hashes in pkg.versions.items():

            # Skip a version we have already seen
            if str(version) in seen_versions:
                continue
            seen_versions.add(str(version))
            meta = {"name": str(version)}
            for key, h in hashes.items():
                meta[key] = h
            versions.append(meta)

        # Repology wants a completely different format for versions
        repology_versions = []
        for version, version_meta in pkg.versions.items():
            try:
                url = pkg.url_for_version(version)
            except BaseException as e:
                url = pkg.all_urls
            meta = {"version": str(version), "downloads": [url]}

            # Is there a develop branch?
            if version.isdevelop():
                meta["branch"] = str(version)

            # We can only get specific deps with concretization, which doesn't always work
            # try:
            #    spec = spack.spec.Spec("%s@%s" %(pkg.name, version))
            #    spec.concretize()
            #    deps = list(spec.dependencies_dict().keys())
            # except:
            #    deps = []
            # meta['dependencies'] = deps
            repology_versions.append(meta)

        variants = []
        if pkg.variants:
            for name, variant in pkg.variants.items():
                if name not in package_variants:
                    package_variants[name] = []
                package_variants[name].append(
                    {"package": pkg.name, "default": variant[0].default}
                )
                variants.append(
                    {
                        "name": name,
                        "default": variant[0].default,
                        "description": variant[0].description,
                    }
                )

        conflicts = []
        if pkg.conflicts:
            for name, conflict_list in pkg.conflicts.items():
                for conflict in conflict_list:
                    conflicts.append(
                        {
                            "name": name,
                            "spec": str(conflict[0]),
                            "description": str(conflict[1]),
                        }
                    )

        aliases = []
        raw_aliases = []
        if pkg.provided:
            for name, alias in pkg.provided.items():
                splitup = str(name).split("@", 1)[0]
                descriptions[splitup] = pkg.format_doc().strip()
                aliases.append({"name": str(name), "alias_for": str(alias)})
                raw_aliases.append(splitup)

        # Get latest version!
        latest_version = spack.version.VersionList(pkg.versions).preferred()
        meta = {
            "name": pkg.name,
            "aliases": aliases,
            "versions": versions,
            "latest_version": str(latest_version),
            "build_system": pkg.build_system_class,
            "conflicts": conflicts,
            "variants": variants,
            "homepage": pkg.homepage,
            "maintainers": pkg.maintainers,
            "patches": patches,
            "resources": resources,
            "description": pkg.format_doc(),
            "dependencies": list(pkg.dependencies.keys()),
        }

        # Keep master lookup of all dependents
        for dep in meta["dependencies"]:
            if dep not in deps_of:
                deps_of[dep] = set()
            deps_of[dep].add(pkg.name)

        metas[pkg.name] = meta

        # Aliases can be linked too
        for alias in raw_aliases:
            metas[alias] = meta

        # Best effort to get urls for versions
        try:
            urls = [pkg.url_for_version(x["name"]) for x in versions]
        except:
            urls = pkg.all_urls

        # Add to repology
        repology_pkg = {
            "name": pkg.name,
            "version": repology_versions,
            "summary": meta["description"],
            "maintainers": meta["maintainers"],
            "licenses": {},
            "downloads": urls,
            "homepages": [pkg.homepage],
            "patches": patches_repology,
            "categories": [],
            "dependencies": meta["dependencies"],
            "alias": meta["aliases"],
        }

        repology["packages"][pkg.name] = repology_pkg
        for alias in raw_aliases:
            repology["packages"][alias] = repology_pkg

    # Save package variants
    outfile = os.path.join(here, "data", "variants.json")
    write_json(package_variants, outfile)

    # Save repology
    outfile = os.path.join(here, "data", "repology.json")
    write_json(repology, outfile)

    # We need one file with all names available
    names = [{'name': p, 'description': metas[p]['description']} for p in metas.keys()]
    names.sort(key=lambda x: x['name'])
    outfile = os.path.join(here, "data", "packages.json")
    write_json(names, outfile)

    # Once we get here, add dependents and save to file
    print("Writing results to file!")
    for pkg, meta in metas.items():

        # Add descriptions to dependent to and deps
        new_deps = []
        for dep in meta["dependencies"]:

            # If we've already seen it via an alias, we're good
            if isinstance(dep, dict):
                new_deps.append(dep)
            else:
                new_deps.append({"name": dep, "description": descriptions.get(dep, "")})

        meta["dependencies"] = new_deps
        meta["dependent_to"] = []

        deps = deps_of.get(pkg, set())
        for dep in list(deps):
            meta["dependent_to"].append(
                {"name": dep, "description": descriptions.get(dep, "")}
            )
        outfile = os.path.join(here, "data", "packages", "%s.json" % pkg)
        write_json(meta, outfile)


if __name__ == "__main__":
    main()
