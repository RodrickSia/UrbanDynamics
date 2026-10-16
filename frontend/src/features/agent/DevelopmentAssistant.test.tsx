import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { DevelopmentAssistant } from './DevelopmentAssistant';
import type { ZoningWorkspace } from '../zoning/useZoning';

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });

test('candidate cards focus their own geometry immediately without calling chat or opening parcel analysis', async () => {
  const candidates = {type:'FeatureCollection',features:[
    {type:'Feature',id:'101',properties:{area_m2:100},geometry:{type:'Polygon',coordinates:[[[106.7,10.8],[106.701,10.8],[106.701,10.801],[106.7,10.8]]]}},
    {type:'Feature',id:'102',properties:{area_m2:200},geometry:{type:'MultiPolygon',coordinates:[[[[106.75,10.85],[106.752,10.85],[106.752,10.853],[106.75,10.85]]]]}},
  ]};
  localStorage.setItem('development-assistant-session','test-session');
  const fetcher=vi.fn(async (url: string) => ({ok:true,json:async()=>url.endsWith('/config')
    ?{enabled:true,model_configured:true,requires_token:false}
    :{session_id:'test-session',messages:[],candidates}}));
  vi.stubGlobal('fetch',fetcher);
  window.matchMedia=vi.fn().mockReturnValue({matches:true,addEventListener:vi.fn(),removeEventListener:vi.fn()});
  Element.prototype.scrollIntoView=vi.fn();
  const onMapAction=vi.fn(()=>[]);
  const workspace={plan:null,development:{},acceptAssistant:vi.fn()} as unknown as ZoningWorkspace;
  render(<DevelopmentAssistant workspace={workspace} onClose={()=>{}} onBusy={()=>{}} onMapAction={onMapAction}/>);
  const first=await screen.findByRole('button',{name:'Show parcel 101 on map'});
  await waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(2));
  fetcher.mockClear();
  fireEvent.click(first);
  expect(onMapAction).toHaveBeenLastCalledWith({type:'focus',bbox:[106.7,10.8,106.701,10.801]});
  fireEvent.click(screen.getByRole('button',{name:'Show parcel 102 on map'}));
  expect(onMapAction).toHaveBeenLastCalledWith({type:'focus',bbox:[106.75,10.85,106.752,10.853]});
  fireEvent.click(first);
  expect(onMapAction).toHaveBeenCalledTimes(3);
  expect(fetcher).not.toHaveBeenCalled();
  expect(workspace.acceptAssistant).not.toHaveBeenCalled();
});
