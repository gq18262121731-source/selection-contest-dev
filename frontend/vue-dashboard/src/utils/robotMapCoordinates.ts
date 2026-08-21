export interface RobotMapViewport {
  width: number;
  height: number;
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  zoom: number;
  panX: number;
  panY: number;
}

export interface RobotMapScreenPoint {
  x: number;
  y: number;
}

export interface RobotMapWorldPoint {
  x: number;
  y: number;
}

export const DEFAULT_ROBOT_MAP_VIEWPORT: RobotMapViewport = {
  width: 900,
  height: 560,
  minX: -6,
  maxX: 6,
  minY: -4,
  maxY: 4,
  zoom: 1,
  panX: 0,
  panY: 0,
};

function dimensions(viewport: RobotMapViewport) {
  const worldWidth = viewport.maxX - viewport.minX;
  const worldHeight = viewport.maxY - viewport.minY;
  const baseScale = Math.min(viewport.width / worldWidth, viewport.height / worldHeight);
  return {
    worldWidth,
    worldHeight,
    scale: baseScale * viewport.zoom,
    centerX: viewport.width / 2 + viewport.panX,
    centerY: viewport.height / 2 + viewport.panY,
  };
}

export function worldToRobotMapScreen(
  point: RobotMapWorldPoint,
  viewport: RobotMapViewport,
): RobotMapScreenPoint {
  const { scale, centerX, centerY } = dimensions(viewport);
  const worldCenterX = (viewport.minX + viewport.maxX) / 2;
  const worldCenterY = (viewport.minY + viewport.maxY) / 2;
  return {
    x: centerX + (point.x - worldCenterX) * scale,
    y: centerY - (point.y - worldCenterY) * scale,
  };
}

export function robotMapScreenToWorld(
  point: RobotMapScreenPoint,
  viewport: RobotMapViewport,
): RobotMapWorldPoint {
  const { scale, centerX, centerY } = dimensions(viewport);
  const worldCenterX = (viewport.minX + viewport.maxX) / 2;
  const worldCenterY = (viewport.minY + viewport.maxY) / 2;
  return {
    x: worldCenterX + (point.x - centerX) / scale,
    y: worldCenterY - (point.y - centerY) / scale,
  };
}

export function clampRobotMapZoom(value: number): number {
  return Math.min(3, Math.max(0.6, value));
}
