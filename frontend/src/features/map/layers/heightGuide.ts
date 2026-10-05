/** A constant-world-height contour of the visible scene, not a distance edge.
 * Custom 3D layers share MapLibre's depth buffer:
 * https://maplibre.org/maplibre-gl-js/docs/API/interfaces/CustomLayerInterface/
 */
export class HeightGuide {
  private readonly program: WebGLProgram;
  private readonly texture: WebGLTexture;
  private readonly framebuffer: WebGLFramebuffer;
  private readonly vao: WebGLVertexArrayObject;
  private width = 0;
  private height = 0;

  constructor(private readonly gl: WebGL2RenderingContext, createProgram: (
    gl: WebGL2RenderingContext, vertex: string, fragment: string,
  ) => WebGLProgram) {
    this.program = createProgram(gl, VERTEX, FRAGMENT);
    this.texture = gl.createTexture()!;
    this.framebuffer = gl.createFramebuffer()!;
    this.vao = gl.createVertexArray()!;
  }

  render(matrix: Float32Array, position: [number, number, number], unitsPerMeter: number, pixelRatio: number): void {
    const gl = this.gl;
    const width = gl.drawingBufferWidth;
    const height = gl.drawingBufferHeight;
    const readFramebuffer = gl.getParameter(gl.READ_FRAMEBUFFER_BINDING);
    const drawFramebuffer = gl.getParameter(gl.DRAW_FRAMEBUFFER_BINDING);
    const activeTexture = gl.getParameter(gl.ACTIVE_TEXTURE);
    gl.activeTexture(gl.TEXTURE0);
    const texture = gl.getParameter(gl.TEXTURE_BINDING_2D);
    const range = gl.getParameter(gl.DEPTH_RANGE) as Float32Array;
    const depthBits = gl.getParameter(gl.DEPTH_BITS);
    const stencilBits = gl.getParameter(gl.STENCIL_BITS);
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, this.framebuffer);
    if (width !== this.width || height !== this.height) {
      this.width = width;
      this.height = height;
      // Match the source depth format, including MSAA default framebuffers.
      const format = stencilBits ? gl.DEPTH_STENCIL : gl.DEPTH_COMPONENT;
      const internal = stencilBits
        ? (depthBits === 32 ? gl.DEPTH32F_STENCIL8 : gl.DEPTH24_STENCIL8)
        : (depthBits === 32 ? gl.DEPTH_COMPONENT32F : gl.DEPTH_COMPONENT24);
      const type = stencilBits
        ? (depthBits === 32 ? gl.FLOAT_32_UNSIGNED_INT_24_8_REV : gl.UNSIGNED_INT_24_8)
        : (depthBits === 32 ? gl.FLOAT : gl.UNSIGNED_INT);
      gl.texImage2D(gl.TEXTURE_2D, 0, internal, width, height, 0, format, type, null);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.framebufferTexture2D(gl.DRAW_FRAMEBUFFER, stencilBits ? gl.DEPTH_STENCIL_ATTACHMENT : gl.DEPTH_ATTACHMENT,
        gl.TEXTURE_2D, this.texture, 0);
      gl.drawBuffers([gl.NONE]);
    }
    // Copy once per rendered frame; no readPixels, CPU mesh rebuild or map reload.
    // https://developer.mozilla.org/en-US/docs/Web/API/WebGL2RenderingContext/blitFramebuffer
    gl.blitFramebuffer(0, 0, width, height, 0, 0, width, height, gl.DEPTH_BUFFER_BIT, gl.NEAREST);
    gl.bindFramebuffer(gl.READ_FRAMEBUFFER, readFramebuffer);
    gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, drawFramebuffer);
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.STENCIL_TEST);
    gl.disable(gl.CULL_FACE);
    gl.depthMask(false);
    gl.enable(gl.BLEND);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(this.program);
    gl.bindVertexArray(this.vao);
    const uniform = (name: string) => gl.getUniformLocation(this.program, name);
    gl.uniformMatrix4fv(uniform('u_inverse'), false, new DOMMatrix(Array.from(matrix)).inverse().toFloat32Array());
    gl.uniform2f(uniform('u_viewport'), width, height);
    gl.uniform2f(uniform('u_depth_range'), range[0], range[1]);
    const clip = new DOMMatrix(Array.from(matrix)).transformPoint({ x: position[0], y: position[1], z: position[2] });
    gl.uniform2f(uniform('u_reference'), (clip.x / clip.w + 1) / 2, (clip.y / clip.w + 1) / 2);
    gl.uniform1f(uniform('u_units'), unitsPerMeter);
    gl.uniform1f(uniform('u_pixel_ratio'), pixelRatio);
    gl.uniform1i(uniform('u_depth'), 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.activeTexture(activeTexture);
  }

  dispose(): void {
    this.gl.deleteProgram(this.program);
    this.gl.deleteTexture(this.texture);
    this.gl.deleteFramebuffer(this.framebuffer);
    this.gl.deleteVertexArray(this.vao);
  }
}

const VERTEX = `#version 300 es
  void main() {
    vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
  }
`;
const FRAGMENT = `#version 300 es
  precision highp float;
  uniform sampler2D u_depth;
  uniform mat4 u_inverse;
  uniform vec2 u_viewport;
  uniform vec2 u_depth_range;
  uniform vec2 u_reference;
  uniform float u_units;
  uniform float u_pixel_ratio;
  out vec4 fragColor;
  float heightAt(vec2 uv) {
    float depth = texture(u_depth, uv).r;
    float z = (depth - u_depth_range.x) / (u_depth_range.y - u_depth_range.x) * 2.0 - 1.0;
    vec4 world = u_inverse * vec4(uv * 2.0 - 1.0, z, 1.0);
    return world.z / world.w / u_units;
  }
  void main() {
    vec2 uv = gl_FragCoord.xy / u_viewport;
    float depth = texture(u_depth, uv).r;
    // Snap to the visible depth sample, using its pixel center for unprojection.
    // This cancels DEM-query/mesh LOD and depth-quantization differences on slopes.
    vec2 reference = (floor(u_reference * u_viewport) + 0.5) / u_viewport;
    float height = heightAt(uv);
    float delta = height - heightAt(reference);
    vec2 texel = 1.0 / u_viewport;
    float dx = min(abs(height - heightAt(uv - vec2(texel.x, 0.0))), abs(height - heightAt(uv + vec2(texel.x, 0.0))));
    float dy = min(abs(height - heightAt(uv - vec2(0.0, texel.y))), abs(height - heightAt(uv + vec2(0.0, texel.y))));
    float slope = length(vec2(dx, dy));
    // No sky, no filled coplanar roof, and no false contour at depth discontinuities.
    if (depth >= 1.0 || texture(u_depth, reference).r >= 1.0 || slope < 0.002) discard;
    float pixels = abs(delta) / slope;
    float alpha = 1.0 - smoothstep(0.4 * u_pixel_ratio, 1.1 * u_pixel_ratio, pixels);
    if (alpha <= 0.0) discard;
    fragColor = vec4(1.0, 0.62, 0.05, alpha * 0.88);
  }
`;
