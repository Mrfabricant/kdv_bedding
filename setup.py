from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

setup(
	name="kdv_bedding",
	version="1.0.0",
	description="KDV Bedding Manufacturing Plant - ERPNext Customisation",
	author="Kazishe Implementation Team",
	author_email="admin@kdv.co.zw",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires,
)
