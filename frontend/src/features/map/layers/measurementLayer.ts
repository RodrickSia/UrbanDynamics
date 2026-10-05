import type {
  CustomLayerInterface,
  CustomRenderMethodInput,
  Map as MapLibreMap,
  MercatorCoordinate,
} from 'maplibre-gl';

import type { MapMode, MeasurementState } from '../types/map';
import {
  createMeasurementSegments,
  createSnapHighlights,
  type MeasurementRenderSegment,
} from '../utils/measurement';
import { localProjectionMatrix, MeasurementProjection, type Position3 } from '../utils/measurementProjection';
import { HeightGuide } from './heightGuide';
import { AreaFill } from './areaFill';
import { createAreaRenderGeometry } from '../utils/measurementAreaRender';

export const MEASUREMENT_LAYER_ID = 'urban-distance-measurement';
export const MEASUREMENT_SURFACE_OFFSET_METERS = 0;
export const MEASUREMENT_LINE_WIDTH_PIXELS = 4;
export const MEASUREMENT_COLORS = {
  distance: [1, 0.36, 0.08, 1],
  horizontal: [0.98, 0.68, 0.12, 1],
  vertical: [0.95, 0.36, 0.14, 1],
  'edge-highlight': [1, 0.32, 0.06, 0.9],
  'area-boundary': [1, 0.47, 0.06, 1],
} as const;
export const FLOATS_PER_LINE_VERTEX = 12;

const FLOATS_PER_POINT_VERTEX = 7;
const LINE_CORNERS = [
  [0, -1],
  [0, 1],
  [1, 1],
  [0, -1],
  [1, 1],
  [1, -1],
] as const;

type MercatorCoordinateConstructor = typeof MercatorCoordinate;

export interface MeasurementLayer extends CustomLayerInterface {
  setMeasurement(measurement: MeasurementState, mode: MapMode): void;
  projection: MeasurementProjection;
}

export function createMeasurementLayer(
  MercatorCoordinateClass: MercatorCoordinateConstructor,
): MeasurementLayer {
  const projection = new MeasurementProjection(MercatorCoordinateClass);
  let origin: Position3 = [0, 0, 0];
  let map: MapLibreMap | null = null;
  let lineProgram: WebGLProgram | null = null;
  let pointProgram: WebGLProgram | null = null;
  let lineBuffer: WebGLBuffer | null = null;
  let pointBuffer: WebGLBuffer | null = null;
  let lineVertexArray: WebGLVertexArrayObject | null = null;
  let pointVertexArray: WebGLVertexArrayObject | null = null;
  let lineVertices: Float32Array<ArrayBufferLike> = new Float32Array();
  let lineRanges: { first: number; count: number; width: number; segmented: boolean }[] = [];
  let geometryDirty = true;
  let pointVertices = new Float32Array();
  let heightGuide: HeightGuide | null = null;
  let guideHeight: { position: Position3; units: number } | null = null;
  let guideActive = false;
  let areaFill: AreaFill | null = null;
  let fillVertices = new Float32Array();
  let fillCell = 1;

  const rebuildGeometry = (measurement: MeasurementState, mode: MapMode) => {
    const renderPoints = measurement.status === 'active' && measurement.preview
      ? [...measurement.points, measurement.preview]
      : measurement.points;
    const first = renderPoints[0];
    origin = first ? projectedPosition(MercatorCoordinateClass, [first.longitude, first.latitude], 0) : [0, 0, 0];
    const isArea = measurement.kind === 'area';
    const areaGeometry = isArea ? createAreaRenderGeometry(renderPoints,mode) : null;
    const segments = isArea ? [] : createMeasurementSegments(renderPoints, mode, measurement.showComponents);
    const groups = [
      { segments: createSnapHighlights(measurement, mode), width: 2.5, segmented: false },
      { segments: areaGeometry?.guides ?? [], width: 1, segmented: true },
      { segments: areaGeometry?.boundary ?? [], width: 3.5, segmented: false },
      { segments: segments.filter(s => s.kind !== 'distance'), width: 1.5, segmented: false },
      { segments: segments.filter(s => s.kind === 'distance'), width: MEASUREMENT_LINE_WIDTH_PIXELS, segmented: true },
    ];
    let firstVertex = 0;
    lineRanges = groups.map(group => {
      const count = group.segments.length * LINE_CORNERS.length;
      const range = { first: firstVertex, count, width: group.width, segmented: group.segmented };
      firstVertex += count;
      return range;
    });
    lineVertices = buildMeasurementLineVertices(MercatorCoordinateClass, groups.flatMap(g => g.segments), origin);
    fillVertices = new Float32Array(areaGeometry?.area.valid ? areaGeometry.area.triangles.flatMap(index => {
      const p = areaGeometry.area.vertices[index];
      const position = projectedPosition(MercatorCoordinateClass,[p.longitude,p.latitude], mode === '3d' ? p.elevationMeters : 0);
      return [...position.map((value,i) => value-origin[i]), ...areaGeometry.area.coordinates[index]];
    }) : []);
    fillCell = areaGeometry?.cellMeters ?? 1;
    geometryDirty = true;
    guideHeight = null;
    guideActive = mode === '3d' && measurement.status === 'active';
    // A world-height reference, independent of distance components, anchors
    // and snap kind. It must also work while hovering before the first click.
    if (mode === '3d' && measurement.status === 'active' && measurement.preview?.elevationAvailable) {
      const p = measurement.preview;
      const position = MercatorCoordinateClass.fromLngLat([p.longitude, p.latitude], p.elevationMeters);
      guideHeight = { position: [position.x - origin[0], position.y - origin[1], position.z - origin[2]],
        units: position.meterInMercatorCoordinateUnits() };
    }
    pointVertices = new Float32Array(renderPoints.flatMap((point, index) => {
      const isPreview = index === renderPoints.length - 1 && measurement.preview === point;
      return pointVertex(
        MercatorCoordinateClass,
        [point.longitude, point.latitude],
        (mode === '3d' ? point.elevationMeters : 0) + MEASUREMENT_SURFACE_OFFSET_METERS,
        isPreview ? [1, 0.3, 0.1, 0.9] : isArea ? [1, 0.47, 0.06, 1] : [0.98, 0.99, 0.98, 1],
        origin,
      );
    }));
    map?.triggerRepaint();
  };

  return {
    id: MEASUREMENT_LAYER_ID,
    type: 'custom',
    renderingMode: '3d',
    projection,
    setMeasurement: rebuildGeometry,
    onAdd(addedMap, gl) {
      map = addedMap;
      lineProgram = createLineProgram(gl);
      pointProgram = createPointProgram(gl);
      lineBuffer = gl.createBuffer();
      pointBuffer = gl.createBuffer();
      lineVertexArray = gl.createVertexArray();
      pointVertexArray = gl.createVertexArray();
      if (!lineBuffer || !pointBuffer || !lineVertexArray || !pointVertexArray) {
        throw new Error('Could not allocate measurement geometry');
      }
      configureLineVertexArray(gl, lineVertexArray, lineBuffer);
      configurePointVertexArray(gl, pointVertexArray, pointBuffer);
      // A style reload allocates new buffers, even when anchors are unchanged.
      geometryDirty = true;
    },
    render(gl, options: CustomRenderMethodInput) {
      if (
        !lineProgram || !pointProgram || !lineBuffer || !pointBuffer
        || !lineVertexArray || !pointVertexArray
      ) return;

      projection.update(options.defaultProjectionData.mainMatrix);
      const matrix = localProjectionMatrix(options.defaultProjectionData.mainMatrix, origin);
      // The viewport-sized depth texture is only needed during active 3D measuring.
      // Keep it across clicks to avoid allocation churn between consecutive segments.
      if (!guideActive && heightGuide) { heightGuide.dispose(); heightGuide = null; }
      if (guideHeight && !heightGuide) heightGuide = new HeightGuide(gl, createProgram);
      if (guideHeight) heightGuide?.render(matrix, guideHeight.position, guideHeight.units, map?.getPixelRatio() ?? 1);
      gl.enable(gl.BLEND);
      gl.blendFuncSeparate(
        gl.SRC_ALPHA,
        gl.ONE_MINUS_SRC_ALPHA,
        gl.ONE,
        gl.ONE_MINUS_SRC_ALPHA,
      );
      // This is an interaction overlay, so terrain and buildings must not hide it.
      gl.disable(gl.DEPTH_TEST);
      gl.disable(gl.CULL_FACE);
      gl.disable(gl.STENCIL_TEST);
      gl.depthMask(false);

      if (fillVertices.length) {
        if (!areaFill) areaFill = new AreaFill(gl,createProgram);
        areaFill.render(matrix,fillVertices,fillCell,geometryDirty);
      } else if (areaFill) { areaFill.dispose(); areaFill = null; }

      gl.useProgram(lineProgram);
      gl.uniformMatrix4fv(gl.getUniformLocation(lineProgram, 'u_matrix'), false, matrix);
      gl.uniform2f(
        gl.getUniformLocation(lineProgram, 'u_viewport'),
        gl.drawingBufferWidth,
        gl.drawingBufferHeight,
      );
      gl.bindVertexArray(lineVertexArray);
      gl.bindBuffer(gl.ARRAY_BUFFER, lineBuffer);
      if (geometryDirty) gl.bufferData(gl.ARRAY_BUFFER, lineVertices, gl.DYNAMIC_DRAW);
      for (const { first, count, width, segmented } of lineRanges) {
        gl.uniform1f(gl.getUniformLocation(lineProgram, 'u_line_width'), width * (map?.getPixelRatio() ?? 1));
        gl.uniform1i(gl.getUniformLocation(lineProgram, 'u_segmented'), segmented ? 1 : 0);
        gl.uniform1f(gl.getUniformLocation(lineProgram, 'u_pixel_ratio'), map?.getPixelRatio() ?? 1);
        gl.drawArrays(gl.TRIANGLES, first, count);
      }

      gl.useProgram(pointProgram);
      gl.uniformMatrix4fv(gl.getUniformLocation(pointProgram, 'u_matrix'), false, matrix);
      gl.uniform1f(gl.getUniformLocation(pointProgram, 'u_point_size'), 12 * (map?.getPixelRatio() ?? 1));
      gl.bindVertexArray(pointVertexArray);
      gl.bindBuffer(gl.ARRAY_BUFFER, pointBuffer);
      if (geometryDirty) gl.bufferData(gl.ARRAY_BUFFER, pointVertices, gl.DYNAMIC_DRAW);
      gl.drawArrays(gl.POINTS, 0, pointVertices.length / FLOATS_PER_POINT_VERTEX);
      geometryDirty = false;

      gl.bindVertexArray(null);
      gl.bindBuffer(gl.ARRAY_BUFFER, null);
      gl.useProgram(null);
      gl.enable(gl.DEPTH_TEST);
      gl.depthMask(true);
    },
    onRemove(_removedMap, gl) {
      areaFill?.dispose();
      areaFill = null;
      heightGuide?.dispose();
      heightGuide = null;
      if (lineVertexArray) gl.deleteVertexArray(lineVertexArray);
      if (pointVertexArray) gl.deleteVertexArray(pointVertexArray);
      if (lineBuffer) gl.deleteBuffer(lineBuffer);
      if (pointBuffer) gl.deleteBuffer(pointBuffer);
      if (lineProgram) gl.deleteProgram(lineProgram);
      if (pointProgram) gl.deleteProgram(pointProgram);
      map = null;
      lineProgram = null;
      pointProgram = null;
      lineBuffer = null;
      pointBuffer = null;
      lineVertexArray = null;
      pointVertexArray = null;
    },
  };
}

export function buildMeasurementLineVertices(
  MercatorCoordinateClass: MercatorCoordinateConstructor,
  segments: MeasurementRenderSegment[],
  origin: Position3 = [0, 0, 0],
): Float32Array {
  return new Float32Array(segments.flatMap((segment) => {
    const color = MEASUREMENT_COLORS[segment.kind];
    const start = projectedPosition(
      MercatorCoordinateClass,
      segment.start,
      segment.startElevation + MEASUREMENT_SURFACE_OFFSET_METERS,
    );
    const end = projectedPosition(
      MercatorCoordinateClass,
      segment.end,
      segment.endElevation + MEASUREMENT_SURFACE_OFFSET_METERS,
    );
    return LINE_CORNERS.flatMap(([progress, side]) => [
      ...start.map((value, index) => value - origin[index]),
      ...end.map((value, index) => value - origin[index]),
      progress,
      side,
      ...color,
    ]);
  }));
}

function projectedPosition(
  MercatorCoordinateClass: MercatorCoordinateConstructor,
  coordinate: [number, number],
  elevation: number,
): [number, number, number] {
  const projected = MercatorCoordinateClass.fromLngLat(coordinate, elevation);
  return [projected.x, projected.y, projected.z];
}

function pointVertex(
  MercatorCoordinateClass: MercatorCoordinateConstructor,
  coordinate: [number, number],
  elevation: number,
  color: readonly number[],
  origin: Position3,
): number[] {
  return [...projectedPosition(MercatorCoordinateClass, coordinate, elevation)
    .map((value, index) => value - origin[index]), ...color];
}

function configureLineVertexArray(
  gl: WebGL2RenderingContext,
  vertexArray: WebGLVertexArrayObject,
  buffer: WebGLBuffer,
): void {
  const stride = FLOATS_PER_LINE_VERTEX * 4;
  gl.bindVertexArray(vertexArray);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  bindAttribute(gl, 0, 3, stride, 0);
  bindAttribute(gl, 1, 3, stride, 3 * 4);
  bindAttribute(gl, 2, 1, stride, 6 * 4);
  bindAttribute(gl, 3, 1, stride, 7 * 4);
  bindAttribute(gl, 4, 4, stride, 8 * 4);
  gl.bindVertexArray(null);
}

function configurePointVertexArray(
  gl: WebGL2RenderingContext,
  vertexArray: WebGLVertexArrayObject,
  buffer: WebGLBuffer,
): void {
  const stride = FLOATS_PER_POINT_VERTEX * 4;
  gl.bindVertexArray(vertexArray);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  bindAttribute(gl, 0, 3, stride, 0);
  bindAttribute(gl, 1, 4, stride, 3 * 4);
  gl.bindVertexArray(null);
}

function bindAttribute(
  gl: WebGL2RenderingContext,
  location: number,
  size: number,
  stride: number,
  offset: number,
): void {
  gl.enableVertexAttribArray(location);
  gl.vertexAttribPointer(location, size, gl.FLOAT, false, stride, offset);
}

function createLineProgram(gl: WebGL2RenderingContext): WebGLProgram {
  return createProgram(gl, `#version 300 es
    layout(location = 0) in vec3 a_start;
    layout(location = 1) in vec3 a_end;
    layout(location = 2) in float a_progress;
    layout(location = 3) in float a_side;
    layout(location = 4) in vec4 a_color;
    uniform mat4 u_matrix;
    uniform vec2 u_viewport;
    uniform float u_line_width;
    out vec4 v_color;
    out vec2 v_distance;
    void main() {
      vec4 start_clip = u_matrix * vec4(a_start, 1.0);
      vec4 end_clip = u_matrix * vec4(a_end, 1.0);
      // Clip segments at the near plane before perspective division. abs(w)
      // would reflect endpoints behind the camera and flip/disappear the strip.
      float start_near = start_clip.z + start_clip.w;
      float end_near = end_clip.z + end_clip.w;
      if (start_near < 0.0 && end_near < 0.0) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        v_color = a_color;
        v_distance = vec2(0.0, 1.0);
        return;
      }
      if (start_near < 0.0) start_clip = mix(start_clip, end_clip, start_near / (start_near - end_near));
      if (end_near < 0.0) end_clip = mix(end_clip, start_clip, end_near / (end_near - start_near));
      vec2 start_ndc = start_clip.xy / max(start_clip.w, 0.000001);
      vec2 end_ndc = end_clip.xy / max(end_clip.w, 0.000001);
      vec2 direction_pixels = (end_ndc - start_ndc) * u_viewport;
      float direction_length = max(length(direction_pixels), 0.000001);
      vec2 normal_pixels = vec2(-direction_pixels.y, direction_pixels.x) / direction_length;
      vec4 current_clip = mix(start_clip, end_clip, a_progress);
      vec2 pixel_offset = normal_pixels * a_side * u_line_width * 0.5;
      current_clip.xy += pixel_offset * 2.0 / u_viewport * current_clip.w;
      gl_Position = current_clip;
      v_color = a_color;
      v_distance = vec2(a_progress * direction_length * 0.5, 1.0) * current_clip.w;
    }
  `, `#version 300 es
    precision highp float;
    in vec4 v_color;
    in vec2 v_distance;
    uniform bool u_segmented;
    uniform float u_pixel_ratio;
    out vec4 fragColor;
    void main() {
      fragColor = v_color;
      if (u_segmented && mod(v_distance.x / v_distance.y / u_pixel_ratio, 16.0) > 9.0)
        fragColor = vec4(1.0);
    }
  `);
}

function createPointProgram(gl: WebGL2RenderingContext): WebGLProgram {
  return createProgram(gl, `#version 300 es
    layout(location = 0) in vec3 a_position;
    layout(location = 1) in vec4 a_color;
    uniform mat4 u_matrix;
    uniform float u_point_size;
    out vec4 v_color;
    void main() {
      gl_Position = u_matrix * vec4(a_position, 1.0);
      gl_PointSize = u_point_size * (a_color.a < 1.0 ? 0.75 : 1.0);
      v_color = a_color;
    }
  `, `#version 300 es
    precision highp float;
    in vec4 v_color;
    out vec4 fragColor;
    void main() {
      vec2 centered = gl_PointCoord * 2.0 - 1.0;
      if (dot(centered, centered) > 1.0) discard;
      float light = 1.0 - smoothstep(0.0, 1.0, length(centered - vec2(-0.3, -0.35)));
      fragColor = vec4(v_color.rgb * (0.72 + light * 0.28), v_color.a);
    }
  `);
}

function createProgram(
  gl: WebGL2RenderingContext,
  vertexSource: string,
  fragmentSource: string,
): WebGLProgram {
  const vertexShader = compileShader(gl, gl.VERTEX_SHADER, vertexSource);
  const fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
  const program = gl.createProgram();
  if (!program) throw new Error('Could not create measurement shader program');
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);
  gl.deleteShader(vertexShader);
  gl.deleteShader(fragmentShader);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(program) ?? 'Could not link measurement shader program');
  }
  return program;
}

function compileShader(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error('Could not create measurement shader');
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(shader) ?? 'Could not compile measurement shader');
  }
  return shader;
}
