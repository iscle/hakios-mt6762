# source this (from bash) before building XNU on Linux
# Everything is found relative to this file. THEOS (default ~/theos) provides the cctools and the
# iOS SDK; XNU_SRC is the kernel tree (xnu/apply.sh creates it).
DARWIN_REDWOOD=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export DARWIN_REDWOOD
export XNU_HOST_OS=$(uname)
if [ "${MACHINE:-}" = MT6762 ]; then
	# Board-local profile; never copy or select the old kernel checkout.
	export MTK_WORKSPACE=${MTK_WORKSPACE:-$(dirname "$DARWIN_REDWOOD")}
	export MTK_REUSE_DEPS=${MTK_REUSE_DEPS:-$MTK_WORKSPACE/toolchain/hackios-build/xnu-deps}
	export MTK_HOST_TOOLS=${MTK_HOST_TOOLS:-$MTK_REUSE_DEPS/host/bin}
	if [ -z "${MTK_LLVM_BIN:-}" ]; then
		if [ ! -x "$MTK_WORKSPACE/toolchain/bin/clang" ]; then
			echo 'MT6762: set MTK_LLVM_BIN to the existing LLVM toolchain.' >&2
			return 1
		fi
		MTK_LLVM_BIN=$(dirname "$(readlink -f "$MTK_WORKSPACE/toolchain/bin/clang")")
	fi
	export MTK_LLVM_BIN
	export THEOS=${THEOS:-$MTK_WORKSPACE/toolchain/theos}
	export XNU_LIBDISPATCH_SOURCE=${XNU_LIBDISPATCH_SOURCE:-$MTK_REUSE_DEPS/libdispatch}
	export XNU_LIBPTHREAD_SOURCE=${XNU_LIBPTHREAD_SOURCE:-$MTK_REUSE_DEPS/libpthread}
	export MTK_AVAILABILITY_SOURCE=${MTK_AVAILABILITY_SOURCE:-$MTK_REUSE_DEPS/AvailabilityVersions}
fi
# On macOS there is no theos: xnu-deps/setup.sh lays out xnu-deps/theos-mac like one (links to the
# cctools of Xcode and to the iPhoneOS 16.5 SDK of github.com/theos/sdks).
if [ "$XNU_HOST_OS" = Darwin ]; then
	export THEOS=${THEOS:-$DARWIN_REDWOOD/xnu-deps/theos-mac}
else
	export THEOS=${THEOS:-$HOME/theos}
fi
export XNU_SRC=${XNU_SRC:-$DARWIN_REDWOOD/xnu-src/xnu-8796.121.2}
export XNUDEPS=$DARWIN_REDWOOD/xnu-deps
export PATH=$XNUDEPS/host/bin:$PATH
export XNU_SDK_PATH=$XNUDEPS/sdk/iPhoneOS16.5.xnu.sdk
export XNU_SDK_VERSION=16.5
export XNU_PLATFORM_PATH=$XNUDEPS/sdk/Platforms/iPhoneOS.platform
if [ "${MACHINE:-}" = MT6762 ]; then
	# The old augmented SDK contains libraries from another checkout. Reuse
	# the immutable theos SDK underneath a new board-local writable overlay.
	export XNU_SDK_PATH=$XNUDEPS/sdk/iPhoneOS16.5.mt6762.sdk
	export PATH=$XNUDEPS/host/bin:$MTK_LLVM_BIN:$THEOS/toolchain/linux/iphone/bin:$PATH
	export MIG=$MTK_HOST_TOOLS/mig MIGCOM=$MTK_HOST_TOOLS/migcom
fi
