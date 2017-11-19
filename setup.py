from setuptools import setup, find_packages

setup(
    name='glacier_upload',

    version='1.0',

    description='AWS Glacier upload utility',

    # The project's main homepage.
    url='https://github.com/tbumi/glacier-upload',

    # Author details
    author='Trapsilo Bumi',
    author_email='tbumi@thpd.io',

    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3 :: Only',
    ],

    keywords='AWS Glacier upload multipart',

    package_dir={'': 'src'},
    packages=find_packages(where='src', exclude=['docs', 'tests']),

    install_requires=['click', 'boto3'],

    setup_requires=['pytest-runner'],

    tests_require=['pytest'],

    entry_points={
        'console_scripts': [
            'upload=glacier_upload.main:main',
        ],
    },
)
