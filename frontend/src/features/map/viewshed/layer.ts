import type { CustomLayerInterface, Map as MapLibreMap } from 'maplibre-gl';
import { direction, frustumCorners, sceneMatrix, type Viewshed } from './math';
import { program, SceneDepth, VisibilityGpu } from './gpu';
import { readScene, type SceneMesh } from './scene';

export const VIEWSHED_LAYER_ID = 'urban-viewsheds';
export interface ViewshedLayer extends CustomLayerInterface {
  update(items: Viewshed[], enabled: boolean): void;
  invalidate(): void;
}
export function createViewshedLayer(
  onStatus: (message: string) => void,
  sceneProvider: (map: MapLibreMap, view: Viewshed) => SceneMesh = readScene,
): ViewshedLayer {
  let map: MapLibreMap,
    gl: WebGL2RenderingContext,
    items: Viewshed[] = [],
    enabled = true,
    revision = 0;
  let depth: SceneDepth | null = null,
    lineProgram: WebGLProgram | null = null,
    buffer: WebGLBuffer | null = null,
    vao: WebGLVertexArrayObject | null = null;
  let lineKey = '',
    lineOffsets: number[] = [];
  const cache = new Map<string, { gpu: VisibilityGpu; mesh: SceneMesh; key: string }>();
  let reported = '';
  const status = (s: string) => {
    if (s !== reported) {
      reported = s;
      onStatus(s);
    }
  };
  const clean = () => {
    cache.forEach((c) => c.gpu.dispose());
    cache.clear();
    depth?.dispose();
    depth = null;
  };
  return {
    id: VIEWSHED_LAYER_ID,
    type: 'custom',
    renderingMode: '3d',
    update(next, active) {
      items = next;
      enabled = active;
      reported = '';
      map?.triggerRepaint();
    },
    invalidate() {
      revision++;
      map?.triggerRepaint();
    },
    onAdd(m, context) {
      map = m;
      gl = context;
      lineProgram = program(
        gl,
        `#version 300 es
        layout(location=0) in vec3 p;uniform mat4 u_matrix;
        void main(){gl_Position=u_matrix*vec4(p,1);}`,
        `#version 300 es
        precision highp float;out vec4 color;void main(){color=vec4(1.0,0.46,0.07,0.85);}`,
      );
      buffer = gl.createBuffer();
      vao = gl.createVertexArray();
      lineKey = '';
      gl.bindVertexArray(vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 12, 0);
      gl.bindVertexArray(null);
    },
    render(context, options) {
      if (!enabled || !items.length) {
        if (cache.size) clean();
        return;
      }
      gl = context;
      const draw = gl.getParameter(gl.DRAW_FRAMEBUFFER_BINDING),
        read = gl.getParameter(gl.READ_FRAMEBUFFER_BINDING);
      const viewport = gl.getParameter(gl.VIEWPORT),
        range = gl.getParameter(gl.DEPTH_RANGE);
      const camera = options.defaultProjectionData.mainMatrix;
      try {
        for (const [id, c] of cache)
          if (!items.some((v) => v.id === id)) {
            c.gpu.dispose();
            cache.delete(id);
          }
        depth ??= new SceneDepth(gl);
        depth.copy();
        const messages: string[] = [];
        for (const view of items) {
          const key = JSON.stringify([
            view.observer,
            direction(view).distance,
            view.horizontalFov,
            view.verticalFov,
            revision,
          ]);
          let entry = cache.get(view.id);
          if (!entry) {
            const mesh = sceneProvider(map, view);
            entry = { gpu: new VisibilityGpu(gl), mesh, key };
            cache.set(view.id, entry);
          } else if (entry.key !== key) {
            entry.mesh = sceneProvider(map, view);
            entry.key = key;
          }
          messages.push(entry.mesh.message);
          entry.gpu.render(view, entry.mesh, camera, depth);
        }
        status(messages.find((m) => m.startsWith('Incomplete')) ?? messages.at(-1) ?? '');
      } catch {
        status('Visibility unavailable · scene/GPU data could not be read');
      } finally {
        gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, draw);
        gl.bindFramebuffer(gl.READ_FRAMEBUFFER, read);
        gl.viewport(...(viewport as [number, number, number, number]));
        gl.depthRange(range[0], range[1]);
      }
      // The frustum is an editing overlay; occlusion colors use actual scene depth.
      gl.disable(gl.DEPTH_TEST);
      gl.disable(gl.STENCIL_TEST);
      gl.disable(gl.CULL_FACE);
      gl.depthMask(false);
      gl.enable(gl.BLEND);
      gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.useProgram(lineProgram);
      gl.bindVertexArray(vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      const nextLineKey = JSON.stringify(items);
      if (nextLineKey !== lineKey) {
        const edges: number[] = [];
        lineOffsets = [];
        for (const view of items) {
          lineOffsets.push(edges.length / 3);
          const corners = frustumCorners(view);
          corners.forEach((p, i) => edges.push(0, 0, 0, ...p, ...p, ...corners[(i + 1) % 4]));
        }
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(edges), gl.DYNAMIC_DRAW);
        lineKey = nextLineKey;
      }
      for (const [i, view] of items.entries()) {
        gl.uniformMatrix4fv(
          gl.getUniformLocation(lineProgram!, 'u_matrix'),
          false,
          sceneMatrix(camera, view),
        );
        gl.drawArrays(gl.LINES, lineOffsets[i], 16);
      }
      gl.bindVertexArray(null);
      gl.bindBuffer(gl.ARRAY_BUFFER, null);
      gl.useProgram(null);
      gl.activeTexture(gl.TEXTURE0);
      gl.depthMask(true);
      gl.enable(gl.DEPTH_TEST);
    },
    onRemove() {
      clean();
      gl.deleteProgram(lineProgram);
      gl.deleteBuffer(buffer);
      gl.deleteVertexArray(vao);
      lineProgram = null;
    },
  };
}
