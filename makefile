PWD := $(shell pwd)
GIT_HASH := $(shell git rev-parse --short HEAD)
TIMESTAMP := $(shell date +%Y%m%d%H%M%S)
RELEASE_ZIP=release_zip
DIST=dist
DIST_RELEASE=dist_release
DIST12=dist12

build_ext:
	python release.py build_ext

dist:
	rm -rf ${DIST}
	mkdir -p ${DIST}
	cp -rf build/lib.*-3*/* ${DIST}/
	cp -rf urecorder/static ${DIST}/urecorder
	cp  urecorder/application.json ${DIST}/urecorder
	cp  urecorder/.env ${DIST}/urecorder
	cp -rf images ${DIST}/images
	cp recorder_app.py ${DIST}/recorder_app.py

webrunner_x86_64_windows_release:dist
	mkdir -p ${DIST_RELEASE}_zip
	zip -r ${DIST_RELEASE}_zip/locustplus_x86_64_windows_release_${GIT_HASH}_${TIMESTAMP}.zip ${DIST_RELEASE}
	cp ${DIST_RELEASE}_zip/locustplus_x86_64_windows_release_${GIT_HASH}_${TIMESTAMP}.zip ../webrunner_dist
	cd ../webrunner_dist && git add . && git commit -am "update locustplus_x86_64_windows_release_${GIT_HASH}" && git push

webrunner_x86_64_linux_release:dist
	mkdir -p ${DIST_RELEASE}_zip
	zip -r ${DIST_RELEASE}_zip/locustplus_x86_64_linux_release_${GIT_HASH}_${TIMESTAMP}.zip ${DIST_RELEASE}
	cp ${DIST_RELEASE}_zip/locustplus_x86_64_linux_release_${GIT_HASH}_${TIMESTAMP}.zip ../webrunner_dist
	cd ../webrunner_dist && git add . && git commit -am "update locustplus_x86_64_linux_release_${GIT_HASH}" && git push

webrunner_aarch_64_linux_release:dist
	mkdir -p ${DIST_RELEASE}_zip
	zip -r ${DIST_RELEASE}_zip/locustplus_aarch_64_linux_release_${GIT_HASH}_${TIMESTAMP}.zip ${DIST_RELEASE}
	cp ${DIST_RELEASE}_zip/locustplus_aarch_64_linux_release_${GIT_HASH}_${TIMESTAMP}.zip ../webrunner_dist
	cd ../webrunner_dist && git add . && git commit -am "update locustplus_aarch_64_linux_release_${GIT_HASH}" && git push

dist_311:
	rm -f dist/webrunnercore/crequestdebug.*
	cp -f webrunnercore/crequestdebug.py dist/webrunnercore/


master:
	python webrunner.py -f examples/httpbin/httpbin.py --master --web-host=0.0.0.0 --host=http://127.0.0.1

worker:
	python webrunner.py -f examples/httpbin/httpbin.py --worker --master-host 127.0.0.1


build_ext12:
	python12.exe release.py build_ext

dist12:build_ext12
	rm -rf ${DIST12}
	mkdir -p ${DIST12}
	cp -rf build/lib.*-cpython-3*/* ${DIST12}/
	rm -rf ${DIST12}/locust
	cp -rf redbird ${DIST12}/
	cp -rf locust ${DIST12}/
	cp -rf locust/static ${DIST12}/locust
	cp -rf locust/templates ${DIST12}/locust
	rm -rf ${DIST12}/webrunnercore/crequestdebug.*
	cp -f webrunnercore/crequestdebug.py ${DIST12}/webrunnercore/
	cp -rf webrunnercore/static ${DIST12}/webrunnercore
	cp -rf webrunnercore/templates ${DIST12}/webrunnercore
	cp -rf webrunnerreport/templates ${DIST12}/webrunnerreport
	cp -rf webscriptplus/templates ${DIST12}/webscriptplus
