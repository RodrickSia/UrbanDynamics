import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { Plan, Scenario } from './types';
import type { SimulationResult } from './simulationTypes';
import { DevelopmentSimulation } from './DevelopmentSimulation';

const { hook } = vi.hoisted(() => ({ hook: vi.fn() }));
vi.mock('./usePlanSimulation', () => ({usePlanSimulation: hook}));
const plan={id:'plan',revision:1} as Plan;
const scenario={id:'proposal',name:'Proposal'} as Scenario;
const result: SimulationResult={id:'run',mode:'native',model_version:'test',context:{development_context:{
  surfaces:{status:'assumed',note:'Unknown ground uses labelled assumptions.',landscape_mode:'preserve',scope:'Selected parcel',unclassified_surface_m2:100,mapped_green_m2:0},
  traffic:{status:'synthetic',source:'Transferred counting reference, not site observations.',note:'Same network and background before/after.',network:'osm_local',radius_m:750,background_vehicles_hour:400,snapshot_id:'hash',captured_at:'2026-10-15'},
  inventory:{status:'estimated',source:'Generated buildings'},capacity:{status:'unknown',source:'No surveyed capacity'},
}},options:[{id:'proposal',state:{metrics:{freshwater_m3_day:20}},comparison:[
  {metric:'freshwater_m3_day',before:10,after:20,delta:10,unit:'m³/day',comparability:'scenario_only'},
],traffic_comparison:[
  {metric:'max_queue_length_m',before:5,after:12,delta:7,unit:'m',comparability:'scenario_only',hour_local:18,seed:2026},
  {metric:'mean_completed_delay_seconds',before:null,after:null,delta:null,unit:'s/completed trip',comparability:'insufficient_data',comparability_reason:'unknown_baseline_occupancy',trip_population_complete:false,
    scenario_values:{before:30,after:10,delta:-20,basis:'Assumed occupancy'}},
]}]};

beforeEach(() => hook.mockReturnValue({result,requesting:false,running:false,run:vi.fn(),action:vi.fn()}));
afterEach(() => {localStorage.clear();vi.clearAllMocks();});

it('shows before, after, change, local OSM and background provenance', () => {
  render(<DevelopmentSimulation plan={plan} scenario={scenario} parcelId="123" disabled={false}/>);
  expect(screen.getAllByRole('columnheader',{name:'Before'})).toHaveLength(2);
  expect(screen.getAllByRole('columnheader',{name:'After'})).toHaveLength(2);
  expect(screen.getByText(/Transferred counting reference/)).toBeInTheDocument();
  expect(screen.getByText(/OSM local extract/)).toBeInTheDocument();
  const water=screen.getByRole('rowheader',{name:/^Water/}).closest('tr')!;
  expect(within(water).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['10','20','10']);
});

it('does not claim a delay improvement when trips are unfinished', () => {
  render(<DevelopmentSimulation plan={plan} scenario={scenario} parcelId="123" disabled={false}/>);
  const delay=screen.getByRole('rowheader',{name:/^Delay per completed trip/}).closest('tr')!;
  expect(within(delay).getByText('Not comparable')).toBeInTheDocument();
  expect(within(delay).queryByText('-20')).not.toBeInTheDocument();
});

it('preserves landscape by default and only exposes redesign percentage on opt-in', async () => {
  render(<DevelopmentSimulation plan={plan} scenario={scenario} parcelId="123" disabled={false}/>);
  expect(screen.getByLabelText('Landscape')).toHaveValue('preserve');
  expect(screen.queryByLabelText('Green / open space (%)')).not.toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText('Landscape'),'redesign');
  expect(screen.getByLabelText('Green / open space (%)')).toBeInTheDocument();
});

it('keeps an unknown building baseline unknown instead of showing a hypothetical zero', () => {
  const unknown=structuredClone(result);
  unknown.options[0].comparison[0]={...unknown.options[0].comparison[0],before:null,after:null,delta:null,
    comparability:'insufficient_data',scenario_values:{before:0,after:20,delta:20,basis:'Unverified baseline'}};
  hook.mockReturnValue({result:unknown,requesting:false,running:false,run:vi.fn(),action:vi.fn()});
  render(<DevelopmentSimulation plan={plan} scenario={scenario} parcelId="123" disabled={false}/>);
  const row=screen.getByRole('rowheader',{name:/^Water/}).closest('tr')!;
  expect(within(row).getAllByRole('cell').map(cell=>cell.textContent)).toEqual(['Unknown','20','Unknown']);
  expect(within(row).getByText('Insufficient data')).toBeInTheDocument();
});

it('labels inferred connection limits and school places as demo assumptions', () => {
  const assumed=structuredClone(result);
  assumed.context!.development_context!.capacity={status:'synthetic',source:'125% of existing demand; not surveyed.',
    water_capacity_m3_day:12.5,wastewater_capacity_m3_day:10,power_capacity_kw:15};
  assumed.context!.development_context!.inventory={status:'estimated',source:'Mapped existing buildings',
    building_count:11,proposed_school_places:719,school_note:'Demo assumption; not surveyed school capacity.'};
  hook.mockReturnValue({result:assumed,requesting:false,running:false,run:vi.fn(),action:vi.fn()});
  render(<DevelopmentSimulation plan={plan} scenario={scenario} parcelId="123" disabled={false}/>);
  expect(screen.getByText(/Demo connection limits: water/)).toHaveTextContent(/12[,.]5/);
  expect(screen.getByText(/11 existing buildings/)).toBeInTheDocument();
  expect(screen.getByText(/Proposed school: 719 assumed student places/)).toBeInTheDocument();
  expect(screen.getByText('Infrastructure capacity · demo assumption')).toBeInTheDocument();
  expect(screen.queryByText(/Available infrastructure capacity: Unknown/)).not.toBeInTheDocument();
});
