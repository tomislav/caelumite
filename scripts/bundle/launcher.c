/*
 * Caelumite.app's main executable (scripts/build_release.py).
 *
 * Runs the bundled interpreter, Contents/MacOS/caelumite-python, on the
 * bundled app code in Contents/Resources/app. The interpreter stays inside
 * Contents/MacOS so macOS names the process after the bundle (menu bar,
 * Dock, Cmd-Tab). A compiled launcher rather than a shell script, because
 * notarization wants the main executable to be a signed Mach-O binary.
 *
 * The bundle must never be written to (its signature would break), so
 * Python is told not to write bytecode (-B; the build precompiles it) and
 * to ignore the user's site-packages (-s) and PYTHONHOME/PYTHONPATH.
 */
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    char raw[PATH_MAX], exe[PATH_MAX];
    uint32_t size = sizeof(raw);
    if (_NSGetExecutablePath(raw, &size) != 0 || realpath(raw, exe) == NULL) {
        fprintf(stderr, "Caelumite: cannot find its own path\n");
        return 1;
    }
    char macos[PATH_MAX];
    strlcpy(macos, dirname(exe), sizeof(macos));

    char python[PATH_MAX], app[PATH_MAX], bin[PATH_MAX];
    snprintf(python, sizeof(python), "%s/caelumite-python", macos);
    snprintf(app, sizeof(app), "%s/../Resources/app", macos);
    snprintf(bin, sizeof(bin), "%s/../Resources/bin", macos);

    /* Bundled tools (7zz) first; Finder launches get a minimal PATH. */
    const char *path = getenv("PATH");
    char newpath[PATH_MAX * 4];
    snprintf(newpath, sizeof(newpath), "%s:%s", bin,
             path && *path ? path : "/usr/bin:/bin:/usr/sbin:/sbin");
    setenv("PATH", newpath, 1);
    unsetenv("PYTHONHOME");
    unsetenv("PYTHONPATH");
    unsetenv("PYTHONSTARTUP");
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);

    if (chdir(app) != 0) {
        perror("Caelumite: cannot open its app folder");
        return 1;
    }

    char **args = calloc((size_t)argc + 4, sizeof(char *));
    if (args == NULL)
        return 1;
    int n = 0;
    args[n++] = python;
    args[n++] = "-B";
    args[n++] = "-s";
    args[n++] = "run_qt.py";
    for (int i = 1; i < argc; i++) {
        /* Finder used to pass a process serial number; Python can't use it. */
        if (strncmp(argv[i], "-psn_", 5) == 0)
            continue;
        args[n++] = argv[i];
    }
    args[n] = NULL;
    execv(python, args);
    perror("Caelumite: cannot start its Python");
    return 1;
}
