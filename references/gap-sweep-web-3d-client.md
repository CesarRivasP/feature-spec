# Gap sweep layer — client-side 3D (WebGL / Three.js / react-three-fiber)

Applies when `_profile.yml gap_sweep_layers:` contains `web-3d-client`.

The base sweep asks what breaks in *logic*. This layer asks what breaks in a
renderer that shares one GPU context with the rest of the page, parses
attacker-supplied binary geometry, and allocates memory the garbage collector
cannot reach.

## Parsing untrusted 3D assets
- **Who authored the file?** A GLB/OBJ/STL/STEP a user uploads is untrusted input in a
  binary format. `GLTFLoader` will follow `buffers[].uri` and `images[].uri` — a
  `data:` URI is inert, an `http(s)://` URI is an outbound request from the viewer to
  a host the uploader chose. State whether external URIs are stripped before parsing.
- **What bounds the parse?** Node count, vertex count, texture resolution, file size.
  A 2 GB GLB with 40M triangles is not a malicious file, it is a CAD export — and it
  freezes the tab identically. Name the numeric limit and what the user sees when the
  file exceeds it. "It will be slow" is not a branch.
- **Does the parse run off the main thread?** Parsing on the main thread blocks input,
  so the UI cannot even render the progress bar that would explain the freeze.
- **What happens on a malformed file?** The loader rejects, throws, or produces a scene
  with zero meshes — three different outcomes, and the third one looks like success.
  Name the branch that distinguishes "parsed, empty" from "parsed, fine".
- **Embedded scripts / extensions?** glTF extensions are ignored silently by default.
  An asset relying on one renders wrong with no error. Say which extensions are supported.

## GPU and memory
- **Who disposes?** Geometries, materials, textures and render targets hold GPU memory
  that is NOT freed when the JS object is collected. Every load/unload path must name
  where `.dispose()` runs. A viewer that reloads models without disposing leaks until
  the context dies — and the symptom appears on the *fifth* model, not the first.
- **WebGL context loss.** `webglcontextlost` fires on GPU driver reset, tab backgrounding
  on some mobile devices, or too many live contexts. The page does not reload itself.
  Name the handler and what the user sees, or state the accepted risk.
- **How many contexts are alive?** Browsers cap them (~8-16). Multiple canvases, or a
  canvas remounted by a router without teardown, exhausts the cap and later canvases
  render black with a console warning nobody reads.
- **Does this run at all without WebGL2?** Name the fallback, or the message.

## react-three-fiber specific
- **State in the render loop.** `setState` inside `useFrame` re-renders 60x/second and
  will melt the page. Per-frame mutation goes through refs, not React state.
- **Does the scene remount on every parent render?** An inline object/array prop to an
  R3F primitive is a new reference each render — the reconciler tears down and rebuilds
  the node, dropping GPU resources and any animation mid-flight.
- **Suspense boundary on every async asset?** `useLoader` suspends. A missing boundary
  is a blank page, not an error.
- **Is `<Canvas>` rendered on the server?** Next.js App Router renders components on the
  server by default; a WebGL canvas cannot. Name the `'use client'` boundary and the
  dynamic import with `ssr: false`, or the build passes and the page throws at runtime.

## Interaction and picking
- **Raycasting cost.** Picking against N meshes is O(N) per pointer move. State N's bound,
  or the acceleration structure (BVH), or throttle the handler — and say which.
- **Does every part have a stable id?** Exploded views, isolation and BOM rows all key off
  node identity. Exporters do not guarantee unique node names; two panels both called
  `Cube.001` silently collapse into one row. Name the id derivation and its uniqueness check.
- **Units.** glTF is metres by default, STL is unitless, CAD exports are often millimetres.
  A viewer that guesses produces a closet 1000x too large. Name where the unit is read
  from, and the branch for when it is absent.

## Anything exported to the user
- **Does an exported STL/DXF/SVG carry real dimensions?** An export that loses scale is
  worse than no export: it is a cut list that will be cut wrong, and nothing on the file
  says so.
- **Client-side download in a sandboxed context.** `<a download>` with a blob URL is
  blocked in some embedded/sandboxed viewers. Name the environment the export runs in.

## Recording the result
Same as the base sweep: every gap either lands in `_facts.yml` (`limits.*`, a new
`changes[]` entry, an `acceptance[]` item) or is written down in doc 01 §Risks as an
accepted risk with its reason. A layer that finds nothing says which kinds it checked.
