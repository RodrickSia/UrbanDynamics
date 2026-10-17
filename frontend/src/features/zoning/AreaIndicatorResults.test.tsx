import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { AreaIndicatorResults } from './AreaIndicatorResults';
import type { AreaIndicators } from './areaIndicatorTypes';

const fixture = {
  area_m2:1000, baseline:{population:394.8,housing_capacity:null,jobs_capacity:null,jobs_balance:null},
  proposal:null, population_source:{status:'estimated',year:2025,coverage_percent:100},
  land_use:[], zoning:[], notes:[], issues:[], transit:{status:'missing',coverage_percent:null},
} as unknown as AreaIndicators;

it('renders older API responses without crashing or claiming the inventory is empty', () => {
  render(<AreaIndicatorResults data={fixture}/>);
  expect(screen.getByRole('table')).toBeInTheDocument();
  expect(screen.getByText(/This API version does not provide/)).toBeInTheDocument();
});

it('shows modeled housing capacity and its source while keeping jobs unknown', () => {
  const data:AreaIndicators = {...fixture,baseline:{...fixture.baseline,housing_capacity:22.7},
    existing_buildings:{status:'estimated',count:3,floor_area_m2:1989.43,source:'Generated',coverage:'unknown'}};
  render(<AreaIndicatorResults data={data}/>);
  expect(screen.getByRole('cell',{name:'22.7'})).toBeInTheDocument();
  expect(screen.getByText(/3 modeled residential buildings/)).toBeInTheDocument();
  expect(screen.getByText(/Existing jobs need commercial/)).toBeInTheDocument();
});

it('explains missing floor counts without saying a housing estimate is available', () => {
  render(<AreaIndicatorResults data={{...fixture,existing_buildings:{status:'partial',count:2,
    floor_area_m2:null,source:'Generated',coverage:'unknown'}}}/>);
  expect(screen.getByText(/missing floor counts/)).toBeInTheDocument();
  expect(screen.queryByText(/Housing estimate:/)).not.toBeInTheDocument();
});
