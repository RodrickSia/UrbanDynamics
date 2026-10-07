type ProgramFactory = (gl: WebGL2RenderingContext, vertex: string, fragment: string) => WebGLProgram;

/** A measurement overlay, not a new map source or terrain mesh. */
export class AreaFill {
  private readonly program: WebGLProgram;
  private readonly buffer: WebGLBuffer;
  private readonly vao: WebGLVertexArrayObject;

  constructor(private readonly gl: WebGL2RenderingContext, createProgram: ProgramFactory) {
    this.program = createProgram(gl, `#version 300 es
      layout(location=0) in vec3 a_position;
      layout(location=1) in vec2 a_meters;
      uniform mat4 u_matrix;
      out vec2 v_meters;
      void main() {
        gl_Position = u_matrix * vec4(a_position, 1.0);
        v_meters = a_meters;
      }
    `, `#version 300 es
      precision highp float;
      in vec2 v_meters;
      uniform float u_cell;
      out vec4 fragColor;
      void main() {
        vec2 grid = v_meters / u_cell;
        vec2 width = max(fwidth(grid), vec2(0.0001));
        vec2 parity = mod(floor(grid), 2.0);
        vec2 edge = smoothstep(vec2(0.0), width, fract(grid));
        vec2 stripe = mix(1.0-parity, parity, edge);
        float checker = stripe.x + stripe.y - 2.0*stripe.x*stripe.y;
        // Below pixel resolution, average the pattern instead of shimmering.
        checker = mix(checker, 0.5, clamp(max(width.x,width.y)-0.5, 0.0, 1.0));
        vec3 color = mix(vec3(1.0,0.47,0.06), vec3(1.0), checker);
        fragColor = vec4(color, 0.56);
      }
    `);
    const buffer = gl.createBuffer(), vao = gl.createVertexArray();
    if (!buffer || !vao) throw new Error('Could not allocate area geometry');
    this.buffer = buffer; this.vao = vao;
    gl.bindVertexArray(vao); gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0,3,gl.FLOAT,false,20,0);
    gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1,2,gl.FLOAT,false,20,12);
    gl.bindVertexArray(null);
  }

  render(matrix: Float32Array, vertices: Float32Array, cell: number, dirty: boolean) {
    const gl = this.gl;
    gl.useProgram(this.program);
    gl.uniformMatrix4fv(gl.getUniformLocation(this.program,'u_matrix'),false,matrix);
    gl.uniform1f(gl.getUniformLocation(this.program,'u_cell'),cell);
    gl.bindVertexArray(this.vao); gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);
    if (dirty) gl.bufferData(gl.ARRAY_BUFFER,vertices,gl.DYNAMIC_DRAW);
    gl.drawArrays(gl.TRIANGLES,0,vertices.length/5);
  }

  dispose() {
    this.gl.deleteBuffer(this.buffer); this.gl.deleteVertexArray(this.vao); this.gl.deleteProgram(this.program);
  }
}
