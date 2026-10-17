# ASCII Engine: ContextDoc on a JavaScript Module

A dependency-free 3D engine that draws with characters: scenes plot points in a `[-1,1]³` world, the engine rotates them through an orbiting camera, projects them in perspective and keeps the nearest one per character cell, picking a character from a brightness ramp (` .:-=+*#%@`).

It is the engine behind the ψ lab easter egg of the [MAuToBlog](https://github.com/Mauto82) theme, and descends from the "Projection" engine ([Mauto82/SPLIT_CORE](https://github.com/Mauto82/SPLIT_CORE)), the first project ContextDoc was used on outside this repository. Only the engine is here: the lab's scenes stay on the blog.

Unlike the Python examples, this one shows ContextDoc on a single JavaScript module whose most important decisions are about *not* doing things: no canvas, no dependencies, no meshes, no validation on the hot path.

## What's in this directory

```
ascii-engine/
├── project.ctx            ← what the engine is for, and what it deliberately leaves to the scenes
├── ascii-engine.js        ← the engine (one ES module, no dependencies)
├── ascii-engine.js.ctx    ← projection, z-buffer, lighting: tensions and conceptual tests
└── index.html             ← demo: a lit torus and a depth-shaded ring
```

## Run it

Any static server from this directory:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/`.

## Use it

```js
import { AsciiEngine } from './ascii-engine.js';

const engine = new AsciiEngine(document.querySelector('pre'));
engine.begin();
engine.lit(x, y, z, nx, ny, nz);   // a point lit by its normal
engine.dot(x, y, z);               // a point shaded by depth
engine.end();                      // writes the frame into the <pre>
```

`yaw`, `pitch` and `distance` move the camera; call `resize()` when the `<pre>` changes size.
