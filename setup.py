from setuptools import setup, Extension

setup(
    name='OMPlex',
    version='0.2.4dev',
    packages=['omplex',],
    license='MIT',
    long_description=open('README.md').read(),
    author="Weston Nielson",
    author_email="wnielson@github",
    url="https://github.com/wnielson/omplex",
    zip_safe=False,
    entry_points = {
        'console_scripts': [
            'omplex = omplex.cmdline:main',
        ]
    },
    data_files = [
        ["omplex/static", ["omplex/static/index.html"]]
    ],
    include_package_data=True,
    install_requires = ['pexpect', 'requests'],
    ext_modules=[Extension(
                    name='libosd',
                    sources=['osd/osd.c', 'osd/libs/libshapes.c', 'osd/libs/oglinit.c'],
                    include_dirs= ['/opt/vc/include', '/opt/vc/include/interface/vmcs_host/linux', '/opt/vc/include/interface/vcos/pthreads', './osd/libs', './osd/fonts'],
                    library_dirs=['/opt/vc/lib'],
                    libraries=['GLESv2', 'jpeg'])]
)

