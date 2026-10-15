// The worker the page starts. It boots the Python the page carries, and then
// does one thing when asked: run the command's own entry point on a file it is
// handed, and hand back what that wrote.
//
// Everything it boots from arrives in the first message, as bytes the page took
// out of itself. The runtime's loader asks for two files by URL -- the
// WebAssembly binary and the standard library -- so while the runtime starts,
// those two URLs, and nothing else, are answered from those bytes. Every other
// request goes to the browser untouched, where it can be seen and counted, and
// once the runtime is up `fetch` is the browser's own again.
//
// The URL they are answered at is under `.invalid`, a name reserved never to
// resolve: if anything ever asked it of the network, the answer would be no.
"use strict";

const RUNTIME = "https://vdi2770-validate.invalid/runtime/";

const script = (bytes) => URL.createObjectURL(new Blob([bytes], {type: "text/javascript"}));

self.onmessage = async (first) => {
  self.onmessage = null;
  const assets = first.data.assets;
  let pyodide;
  try {
    const own = new Map([
      [RUNTIME + "pyodide.asm.wasm", ["application/wasm", assets["pyodide.asm.wasm"]]],
      [RUNTIME + "python_stdlib.zip", ["application/zip", assets["python_stdlib.zip"]]],
    ]);
    const browserFetch = self.fetch;
    self.fetch = function (input, init) {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const hit = own.get(url);
      if (hit) return Promise.resolve(new Response(hit[1], {headers: {"Content-Type": hit[0]}}));
      return browserFetch.call(self, input, init);
    };
    try {
      importScripts(script(assets["pyodide.asm.js"]));
      importScripts(script(assets["pyodide.js"]));
      pyodide = await loadPyodide({
        indexURL: RUNTIME,
        packageBaseUrl: RUNTIME,
        lockFileContents: new TextDecoder().decode(assets["pyodide-lock.json"]),
      });
    } finally {
      self.fetch = browserFetch;
    }
    pyodide.unpackArchive(assets["app.zip"], "zip", {extractDir: "/app"});
    pyodide.runPython("import sys; sys.path.insert(0, '/app')");
    const page = pyodide.pyimport("vdi2770_page");
    const runtime = page.versions().toJs({dict_converter: Object.fromEntries});
    runtime.runtime = "Pyodide " + pyodide.version;
    self.onmessage = (asked) => {
      const {name, bytes, json} = asked.data;
      let result;
      try {
        result = page.check(name, new Uint8Array(bytes), json);
        const [argv, stdout, stderr, code] = result.toJs();
        postMessage({type: "result", name, argv, stdout, stderr, code}, [stdout.buffer, stderr.buffer]);
      } catch (e) {
        postMessage({type: "failed", message: String(e)});
      } finally {
        if (result) result.destroy();
      }
    };
    postMessage({type: "ready", runtime});
  } catch (e) {
    postMessage({type: "failed", message: String(e)});
  }
};
