import { describe, expect, it } from 'vitest';
import { floodLocationDetails } from '../datasets/floodLocation';

describe('reported flood locations', () => {
  it('distinguishes a historical neighbourhood from the current ward and an exact address', () => {
    const input = {
      location: '  Phường Hiệp Bình Chánh ,  khu phố 3  '.normalize('NFD'),
      reported_ward: 'Phường Hiệp Bình Chánh',
      reported_district: 'Thủ Đức',
      current_admin_unit: 'Phường Hiệp Bình',
      geocoding_method: 'Area point',
      spatial_precision: 'Medium',
      depth_max_cm: 300,
    };
    const result = floodLocationDetails(input);
    expect(result.location).toBe('Phường Hiệp Bình Chánh, khu phố 3, Thủ Đức');
    expect(result.current_admin_unit).toBe('Phường Hiệp Bình');
    expect(result.location_accuracy).toBe('Approximate area · medium precision');
    expect(result.depth_max_cm).toBe(300);
    expect(input.location).toContain('  ');
  });
  it('adds missing historical context to Cầu Ông Dầu without treating the name as an exact bridge pin', () => {
    const result = floodLocationDetails({
      location: 'Cầu Ông Dầu',
      reported_ward: 'Phường Hiệp Bình Phước',
      reported_district: 'Thủ Đức',
      geocoding_method: 'Area point',
      spatial_precision: 'Low',
    });
    expect(result.location).toBe('Cầu Ông Dầu, Phường Hiệp Bình Phước, Thủ Đức');
    expect(result.location_accuracy).toBe('Approximate area · low precision');
  });
  it('does not invent administrative units or upgrade unknown accuracy', () => {
    expect(floodLocationDetails({ location: 'Unknown' }).location_accuracy).toBe(
      'Location accuracy unknown',
    );
    expect(
      floodLocationDetails({ location: 'A', spatial_precision: 'Hugh' }).location_accuracy,
    ).toBe('Location accuracy unknown');
    expect(
      floodLocationDetails({ location: 'A', geocoding_method: 'Street point' }).location_accuracy,
    ).toBe('Approximate street location');
  });
});
