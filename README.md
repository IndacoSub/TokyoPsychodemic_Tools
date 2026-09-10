# TokyoPsychodemic_Tools

A suite of tools used by Team DAIX for the *unofficial* Italian translation of Tokyo Psychodemic.

> **AI-assisted development**
>
> Parts of this repository were developed with assistance from generative AI. AI was used during implementation, debugging, diagnostic analysis, Unity serialization research, and development of supporting tooling. The generated code was reviewed, adapted, and tested against the actual target files and game environment.

## Usage

You'll need to edit `script_base.txt` and `script.py` in order to make the pipeline work:

Among other data, `script_base.txt` contains the relative locations of your dumped (and presumably edited) files, whereas `script.py` may rely on external tools whose full path you'll need to edit or specify, and/or use different paths than those specified in general.

Once you've made those changes, you can run `script_gui.py` in order to easily select which files from `script_base.txt` should be compiled, and then generate the new `script.py`. Finally, just use `BUILD.bat` to compile.

## License

This repository is licensed under the ISC License.

## Credits

	 "TOKYO PSYCHODEMIC" is a registered trademark of Gravity Co., Ltd and GRAVITY GAME ARISE Co., Ltd.
     We are not in any way affiliated or associated with them.