"""
Utils.macos.wizard
Adapts upstream's wizard "Choose Proton Version" step to macOS.

Wizard tools always run in the game's CrossOver bottle on macOS (see
Utils.macos.launch.tool_prefix_env), so the step's Proton picker, shared and
winetricks-style prefix options have nothing to choose. The step keeps its
launch arguments and environment variables, preselects the game prefix and
says which bottle the tool will run in.
"""

from __future__ import annotations


def adapt_proton_step(step) -> None:
    """Rework a ``wizards_qt.proton_step.ProtonStepWidget`` for CrossOver."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    from Utils.macos.crossover import bottle_for_path

    step._no_versions_label.hide()
    # Each option sits in a holder row with its "?" marker; hide whole rows.
    for control in (step._shared_chk, step._winetricks_chk, step._game_chk):
        if control is not None and control.parentWidget() is not None:
            control.parentWidget().hide()
    step._proton_combo.parentWidget().hide()   # picker + custom build + delete

    game = step._game
    try:
        prefix = game.get_prefix_path() if hasattr(game, "get_prefix_path") else None
    except Exception:
        prefix = None
    bottle = bottle_for_path(prefix)
    if bottle is not None:
        if step._game_chk is not None:
            step._game_chk.setChecked(True)
        text = step.tr("{0} runs in the game's CrossOver bottle '{1}'.").format(
            step._tool_display_name, bottle.name)
    else:
        text = step.tr("This game has no CrossOver bottle yet - set it in "
                       "Configure Game first.")
    note = QLabel(text)
    note.setAlignment(Qt.AlignHCenter)
    note.setWordWrap(True)
    step.layout().insertWidget(1, note)

    # Every tool runs in the game's bottle on macOS, so the step always
    # answers "the game's prefix" - also for wizards that don't offer that
    # option on Linux (allow_game_prefix=False leaves no checkbox, and the
    # step would otherwise insist on a Proton build).
    from Utils.executables.launch import PREFIX_MODE_GAME
    step._current_prefix_mode = lambda: PREFIX_MODE_GAME
    step._update_proton_row_state = (
        lambda: step._continue_btn.setEnabled(bottle is not None))
    step._update_proton_row_state()

    # "Always use these settings": the remembered choice is the game's
    # prefix, which upstream rejects for wizards without that option ("The
    # saved game prefix is unavailable") and then stops auto-skipping. Here
    # the bottle is that prefix, so drop that warning and skip as upstream
    # would. Other warnings (a missing 64-bit exe) still stop the wizard.
    unavailable = step.tr("The saved game prefix is unavailable. Choose another "
                          "prefix setting.")
    if (bottle is not None and step._remembered
            and step._remember_warning == unavailable):
        for label in step.findChildren(QLabel):
            if label.text() == unavailable:
                label.hide()
        step._remember_warning = ""
        step._auto_skip_pending = True


# Wizards that cannot work on macOS, keyed by WizardTool.dialog_class_path,
# with the reason. They are dropped from the Wizard menu there (added to
# wizards_qt.EXCLUDED). Everything else either runs its tool in the game's
# CrossOver bottle or does its work in Python.
MACOS_UNSUPPORTED: dict[str, str] = {
    "wizards.reshade.ReShadeWizard":
        "installs d3dcompiler_47 with Linux winetricks; ReShade can't hook "
        "games rendering through CrossOver's D3DMetal",
    "wizards.bodyslide_linux.BodySlideLinuxWizard":
        "runs the Linux build of BodySlide",
    "wizards.bodyslide_linux.OutfitStudioLinuxWizard":
        "runs the Linux build of Outfit Studio",
    "wizards.ttw.TTWInstallerWizard": "runs the native Linux MPI installer",
    "wizards.bsa_decompressor.BSADecompressorWizard":
        "runs the native Linux MPI installer",
    "wizards.esm_fixes.ESMFixesWizard": "runs the native Linux MPI installer",
    "wizards.me3_install.Me3InstallWizard": "installs the Linux build of me3",
    "wizards.regulation_merge.RegulationMergeWizard":
        "runs the linux-x64 build of WitchyBND",
    "wizards_qt.yeetpatch_view.YeetPatchView": "runs the Linux build of YeetPatch",
    "wizards.vramr.VRAMrWizard": "converts textures with texconv through Proton",
    "wizards.bendr_parallaxr.BENDrWizard":
        "converts textures with texconv through Proton",
    "wizards.bendr_parallaxr.ParallaxRWizard":
        "converts textures with texconv through Proton",
    "wizards.bethesda_synthesis.SynthesisWizard":
        "builds its own Proton prefix with .NET; it has no CrossOver path",
}
