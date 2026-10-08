import { direction, observerMatrix, sceneMatrix, type Viewshed } from './math';
import type { SceneMesh } from './scene';

export function program(gl: WebGL2RenderingContext, vertex: string, fragment: string) {
  const shaders: WebGLShader[] = [];
  const p = gl.createProgram();
  if (!p) throw new Error('Viewshed program allocation failed');
  try {
    [gl.VERTEX_SHADER, gl.FRAGMENT_SHADER].forEach((type, i) => {
      const shader = gl.createShader(type)!;
      if (!shader) throw new Error('Viewshed shader allocation failed');
      shaders.push(shader);
      gl.shaderSource(shader, i ? fragment : vertex);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        const error = gl.getShaderInfoLog(shader);
        throw new Error(error ?? 'Viewshed shader failed');
      }
      gl.attachShader(p, shader);
    });
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
      throw new Error('Viewshed program failed');
    }
    return p;
  } catch (error) {
    gl.deleteProgram(p);
    throw error;
  } finally {
    shaders.forEach((s) => gl.deleteShader(s));
  }
}
const SCREEN_VERTEX = `#version 300 es
void main(){vec2 p=vec2(float((gl_VertexID<<1)&2),float(gl_VertexID&2));gl_Position=vec4(p*2.0-1.0,0,1);}`;
const RESULT_FRAGMENT = `#version 300 es
precision highp float;
uniform sampler2D u_scene; uniform sampler2D u_shadow;
uniform mat4 u_inverse; uniform mat4 u_observer;
uniform vec2 u_viewport; uniform vec2 u_depthRange; uniform bool u_complete;
uniform float u_far; uniform float u_grid;
out vec4 color;
void main(){
  vec2 uv=gl_FragCoord.xy/u_viewport; float depth=texture(u_scene,uv).r;
  if(depth>=u_depthRange.y-0.0000001) discard;
  vec4 local=u_inverse*vec4(uv*2.0-1.0,(depth-u_depthRange.x)/(u_depthRange.y-u_depthRange.x)*2.0-1.0,1.0);
  local/=local.w;
  vec3 normal=normalize(cross(dFdx(local.xyz),dFdy(local.xyz)));
  vec4 light=u_observer*local;
  if(light.w<=0.1) discard;
  vec3 q=light.xyz/light.w;
  if(any(greaterThan(abs(q),vec3(1.0)))) discard;
  float nearest=texture(u_shadow,q.xy*0.5+0.5).r;
  // Compare metres, not a fixed nonlinear depth epsilon (which grows to tens
  // of metres at long range). Slope-scaled tolerance accounts for sampling
  // disagreement between the DEM analysis grid and the displayed terrain.
  float nearestMeters=0.1*u_far/(u_far-nearest*(u_far-0.1));
  float incidence=max(0.15,abs(dot(normal,normalize(local.xyz))));
  float tolerance=min(5.0,max(0.2,u_grid*0.15)/incidence);
  bool blocked=light.w>nearestMeters+tolerance;
  if(!blocked&&!u_complete) discard;
  // Hatching differentiates blocked regions without relying on color alone.
  float hatch=step(0.5,fract((gl_FragCoord.x+gl_FragCoord.y)/10.0));
  color=blocked?vec4(0.94,0.18,0.13,0.30+0.12*hatch):vec4(0.13,0.78,0.38,0.38);
}`;

/** One scene-depth copy shared by all analyses; no readPixels or CPU screen geometry. */
export class SceneDepth {
  texture: WebGLTexture;
  private fbo: WebGLFramebuffer;
  private size = '';
  constructor(private gl: WebGL2RenderingContext) {
    this.texture = gl.createTexture()!;
    this.fbo = gl.createFramebuffer()!;
  }
  copy() {
    const gl = this.gl,
      w = gl.drawingBufferWidth,
      h = gl.drawingBufferHeight;
    const read = gl.getParameter(gl.READ_FRAMEBUFFER_BINDING),
      draw = gl.getParameter(gl.DRAW_FRAMEBUFFER_BINDING);
    const depth = gl.getParameter(gl.DEPTH_BITS),
      stencil = gl.getParameter(gl.STENCIL_BITS);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    // READ and DRAW bindings can differ after the map's offscreen terrain pass.
    // Copy the depth of the scene currently being drawn, not a stale read target.
    gl.bindFramebuffer(gl.READ_FRAMEBUFFER, draw);
    gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, this.fbo);
    const size = `${w}:${h}:${depth}:${stencil}`;
    if (size !== this.size) {
      gl.texImage2D(
        gl.TEXTURE_2D,
        0,
        stencil
          ? depth === 32
            ? gl.DEPTH32F_STENCIL8
            : gl.DEPTH24_STENCIL8
          : depth === 32
            ? gl.DEPTH_COMPONENT32F
            : gl.DEPTH_COMPONENT24,
        w,
        h,
        0,
        stencil ? gl.DEPTH_STENCIL : gl.DEPTH_COMPONENT,
        stencil
          ? depth === 32
            ? gl.FLOAT_32_UNSIGNED_INT_24_8_REV
            : gl.UNSIGNED_INT_24_8
          : depth === 32
            ? gl.FLOAT
            : gl.UNSIGNED_INT,
        null,
      );
      configureTexture(gl);
      gl.framebufferTexture2D(
        gl.DRAW_FRAMEBUFFER,
        stencil ? gl.DEPTH_STENCIL_ATTACHMENT : gl.DEPTH_ATTACHMENT,
        gl.TEXTURE_2D,
        this.texture,
        0,
      );
      gl.drawBuffers([gl.NONE]);
      if (gl.checkFramebufferStatus(gl.DRAW_FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE)
        throw new Error('Scene depth unavailable');
      this.size = size;
    }
    // https://developer.mozilla.org/en-US/docs/Web/API/WebGL2RenderingContext/blitFramebuffer
    gl.blitFramebuffer(0, 0, w, h, 0, 0, w, h, gl.DEPTH_BUFFER_BIT, gl.NEAREST);
    gl.bindFramebuffer(gl.READ_FRAMEBUFFER, read);
    gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, draw);
  }
  dispose() {
    this.gl.deleteTexture(this.texture);
    this.gl.deleteFramebuffer(this.fbo);
  }
}
function configureTexture(gl: WebGL2RenderingContext) {
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
}
export class VisibilityGpu {
  private shadow: WebGLTexture;
  private fbo: WebGLFramebuffer;
  private buffer: WebGLBuffer;
  private vao: WebGLVertexArrayObject;
  private screenVao: WebGLVertexArrayObject;
  private depthProgram: WebGLProgram;
  private resultProgram: WebGLProgram;
  private count = 0;
  private lastMatrix = '';
  private mesh: SceneMesh | null = null;
  constructor(private gl: WebGL2RenderingContext) {
    this.depthProgram = program(
      gl,
      `#version 300 es
      layout(location=0) in vec3 position; uniform mat4 u_matrix;
      void main(){gl_Position=u_matrix*vec4(position,1.0);}`,
      `#version 300 es
      precision highp float; void main(){}`,
    );
    try {
      this.resultProgram = program(gl, SCREEN_VERTEX, RESULT_FRAGMENT);
    } catch (error) {
      gl.deleteProgram(this.depthProgram);
      throw error;
    }
    this.shadow = gl.createTexture()!;
    this.fbo = gl.createFramebuffer()!;
    this.buffer = gl.createBuffer()!;
    this.vao = gl.createVertexArray()!;
    this.screenVao = gl.createVertexArray()!;
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 12, 0);
    gl.bindVertexArray(null);
    const old = gl.getParameter(gl.FRAMEBUFFER_BINDING);
    gl.bindTexture(gl.TEXTURE_2D, this.shadow);
    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      gl.DEPTH_COMPONENT24,
      1024,
      1024,
      0,
      gl.DEPTH_COMPONENT,
      gl.UNSIGNED_INT,
      null,
    );
    configureTexture(gl);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.TEXTURE_2D, this.shadow, 0);
    gl.drawBuffers([gl.NONE]);
    gl.readBuffer(gl.NONE);
    const ready = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
    gl.bindFramebuffer(gl.FRAMEBUFFER, old);
    if (!ready) {
      this.dispose();
      throw new Error('Viewshed depth buffer unavailable');
    }
  }
  render(view: Viewshed, mesh: SceneMesh, camera: ArrayLike<number>, depth: SceneDepth) {
    const gl = this.gl,
      observer = observerMatrix(view),
      matrixKey = Array.from(observer).join(',');
    const draw = gl.getParameter(gl.DRAW_FRAMEBUFFER_BINDING),
      read = gl.getParameter(gl.READ_FRAMEBUFFER_BINDING);
    const viewport = gl.getParameter(gl.VIEWPORT),
      range = gl.getParameter(gl.DEPTH_RANGE);
    if (this.mesh !== mesh || matrixKey !== this.lastMatrix) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo);
      gl.viewport(0, 0, 1024, 1024);
      gl.depthRange(0, 1);
      gl.disable(gl.SCISSOR_TEST);
      gl.disable(gl.STENCIL_TEST);
      gl.disable(gl.BLEND);
      gl.disable(gl.CULL_FACE);
      gl.enable(gl.DEPTH_TEST);
      gl.depthFunc(gl.LEQUAL);
      gl.depthMask(true);
      gl.clearDepth(1);
      gl.clear(gl.DEPTH_BUFFER_BIT);
      gl.useProgram(this.depthProgram);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.depthProgram, 'u_matrix'), false, observer);
      gl.bindVertexArray(this.vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
      if (this.mesh !== mesh) {
        gl.bufferData(gl.ARRAY_BUFFER, mesh.vertices, gl.STATIC_DRAW);
        this.count = mesh.vertices.length / 3;
        this.mesh = mesh;
      }
      gl.drawArrays(gl.TRIANGLES, 0, this.count);
      this.lastMatrix = matrixKey;
      gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, draw);
      gl.bindFramebuffer(gl.READ_FRAMEBUFFER, read);
      gl.viewport(...(viewport as [number, number, number, number]));
      gl.depthRange(range[0], range[1]);
    }
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.STENCIL_TEST);
    gl.disable(gl.CULL_FACE);
    gl.depthMask(false);
    gl.enable(gl.BLEND);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(this.resultProgram);
    gl.bindVertexArray(this.screenVao);
    const u = (n: string) => gl.getUniformLocation(this.resultProgram, n);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, depth.texture);
    gl.uniform1i(u('u_scene'), 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.shadow);
    gl.uniform1i(u('u_shadow'), 1);
    gl.uniformMatrix4fv(
      u('u_inverse'),
      false,
      new DOMMatrix(Array.from(sceneMatrix(camera, view))).inverse().toFloat32Array(),
    );
    gl.uniformMatrix4fv(u('u_observer'), false, observer);
    gl.uniform2f(u('u_viewport'), gl.drawingBufferWidth, gl.drawingBufferHeight);
    gl.uniform2f(u('u_depthRange'), range[0], range[1]);
    gl.uniform1i(u('u_complete'), mesh.complete ? 1 : 0);
    gl.uniform1f(u('u_far'), direction(view).distance);
    gl.uniform1f(u('u_grid'), mesh.step);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.activeTexture(gl.TEXTURE0);
  }
  dispose() {
    const gl = this.gl;
    gl.deleteTexture(this.shadow);
    gl.deleteFramebuffer(this.fbo);
    gl.deleteBuffer(this.buffer);
    gl.deleteVertexArray(this.vao);
    gl.deleteVertexArray(this.screenVao);
    gl.deleteProgram(this.depthProgram);
    gl.deleteProgram(this.resultProgram);
  }
}
