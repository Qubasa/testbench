import setuptools

setuptools.setup(
    name='testbench',
    version = "2.0",
    description='Rechnernetze test utils',
    packages=["testbench"],
    entry_points={
        'console_scripts': [
            'testbench = testbench.testrunner:main',
        ]
    }
)
