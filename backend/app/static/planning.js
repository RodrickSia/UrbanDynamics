/* Standalone API preview; team map consumes the same results and GeoJSON. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id), base = '/api/v1/planning';
  const labels = {housing_units:'Căn hộ',residents:'Cư dân',floor_area_m2:'Diện tích sàn',green_m2:'Đất xanh',impervious_m2:'Không thấm',freshwater_m3_day:'Nước cấp',wastewater_m3_day:'Nước thải',energy_kwh_day:'Điện năng',power_peak_kw:'Đỉnh điện chung',person_trips_day:'Chuyến người',unretained_runoff_m3:'Runoff screening',school_demand_students:'Nhu cầu chỗ học',school_served_students:'Được phân bổ chỗ học',school_unserved_students:'Chưa được phân bổ chỗ học',school_mean_assigned_walk_m:'Khoảng đi bộ của nhóm được phân bổ',mean_shaded_receiver_m2:'Diện tích bóng trung bình',mean_shaded_neighbour_m2:'Bóng ngoài khu đất',node_flooding_m3:'Tràn nút SWMM',runoff_peak_m3_s:'Đỉnh runoff SWMM',background_completed_delay_seconds:'Delay xe nền hoàn thành',mean_completed_delay_seconds:'Delay mọi xe hoàn thành',max_queue_length_m:'Hàng chờ tối đa',completed_vehicles:'Xe hoàn thành',unfinished_vehicles:'Xe chưa hoàn thành',undeparted_vehicles:'Xe chưa xuất phát'};
  let presets, result, analysisResult, jobId, generation = 0, timer;
  const number = value => value == null ? 'Chưa biết' : Number(value).toLocaleString('vi-VN', {maximumFractionDigits:2});
  const status = (text, error=false) => { $('status').textContent = text; $('status').dataset.error = String(error); };
  async function api(path, body) {
    const response = await fetch(base+path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail));
    return value;
  }
  function pending(active) { $('run').disabled=active; $('load-preset').disabled=active; $('preflight').disabled=active; $('restore').disabled=active; $('cancel').disabled=!active; $('retry').disabled=true; }
  function savedInput(study){
    const payload=study.inputs;
    $('input').value=JSON.stringify(payload,null,2);
    $('study-mode').value=payload.background_snapshot?'inclusive':payload.resident_transfers?.length?'rehousing':payload.projects.length===1?'single_site':payload.mode;
    $('preset-description').textContent=`Đang xem đầu vào đã lưu: ${payload.mode==='site_selection'?'so vị trí thay thế':'tác động cộng dồn'}, ${payload.projects.length} dự án. Quy mô và điều kiện lấy từ JSON của revision này.`;
  }
  function invalidate() { generation++; clearTimeout(timer); result=null; analysisResult=null; $('results').hidden=true; pending(false); }
  function preset() {
    invalidate();
    const payload = structuredClone(presets[$('study-mode').value]);
    payload.criteria = [{metric:'school_unserved_students',direction:'minimize'}, {metric:'power_peak_kw',direction:'minimize'}];
    payload.uncertainty={engine:'native',seeds:[2026,2027,2028],cases:[
      {id:'low',source:'Synthetic lower trip-generation assumption; fixed building plan and rain',level:'low'},
      {id:'high',source:'Synthetic higher trip-generation assumption; fixed building plan and rain',level:'high'},
      {id:'lower_capacity',source:'Synthetic shared utility capacities at 80 percent; not measured capacities',utility_capacity_scale:.8}]};
    $('input').value=JSON.stringify(payload,null,2);
    $('preset-description').textContent=($('study-mode').value==='single_site'?'Mẫu một khu đất: 200 căn / 600 cư dân / 24.000 m² sàn, dùng cùng nền vùng với study nhiều khu đất. ':['rehousing','inclusive'].includes($('study-mode').value)?'Mẫu di dời: A có 40 căn / 100 cư dân hiện hữu; C có 150 căn / 300 cư dân sau xây, bao gồm 100 người từ A và 200 người từ ngoài vùng; B là trường 600 chỗ. ':payload.mode==='site_selection'?'Mẫu so vị trí giữ 200 căn / 600 cư dân / 24.000 m² sàn. ':'Mẫu cộng dồn: A 200 căn, B trường 600 chỗ, C 150 căn. ')+'Điều kiện chung: mưa 60 mm trong 1 giờ, giao thông 7h và 18h. Chỉnh building plan hoặc điều kiện trong JSON.';
    status('Đã nạp mẫu. Tiêu chí minh họa: số học sinh chưa được phục vụ và đỉnh tải điện; có thể thay đổi trong JSON.');
  }
  function selected() { return $('option').value === 'baseline' ? {id:'baseline',title:'Hiện trạng',state:result.baseline,comparison:[]} : [...result.options,...result.phases].find(o=>o.id===$('option').value); }
  function element(name, attributes, text) { const node=document.createElementNS('http://www.w3.org/2000/svg',name); for(const [key,value] of Object.entries(attributes||{}))node.setAttribute(key,String(value)); if(text!==undefined)node.textContent=text; return node; }
  function map(option) {
    const svg=$('map'); svg.replaceChildren();
    let points=result.inputs.study_area.coordinates[0];
    if($('map-extent').value==='impact'){
      const coordinates=value=>typeof value[0]==='number'?[value]:value.flatMap(coordinates);
      const geometryPoints=g=>g.type==='GeometryCollection'?g.geometries.flatMap(geometryPoints):coordinates(g.coordinates);
      const features=[...result.spatial_artifacts.parcels.features,...(result.spatial_artifacts.roads?.features||[])];
      for(const state of [result.baseline,...result.options.map(o=>o.state)])features.push(...state.school_services.map.features,...state.shadow.map.features,...(state.drainage?.catchments||[]).flatMap(c=>[...c.map.features,...(c.link_map?.features||[])]));
      points=features.flatMap(f=>geometryPoints(f.geometry));
    }
    const xs=points.map(p=>p[0]), ys=points.map(p=>p[1]);
    let left=Math.min(...xs),right=Math.max(...xs),bottom=Math.min(...ys),top=Math.max(...ys);
    const padX=Math.max((right-left)*.08,.0001),padY=Math.max((top-bottom)*.12,.0001);left-=padX;right+=padX;bottom-=padY;top+=padY;
    const cosine=Math.cos((top+bottom)*Math.PI/360),scale=Math.min(660/((right-left)*cosine),310/(top-bottom));
    const ox=350-(right-left)*cosine*scale/2,oy=175+(top-bottom)*scale/2;
    const project=p=>[ox+(p[0]-left)*cosine*scale,oy-(p[1]-bottom)*scale];
    const path=coordinates=>coordinates.map((p,i)=>`${i?'L':'M'}${project(p).join(',')}`).join(' ')+' Z';
    function draw(feature, color, fill='none', width=2) {
      const g=feature.geometry;if(!g)return;
      const properties=feature.properties||{};
      if(g.type==='GeometryCollection'){for(const geometry of g.geometries)draw({...feature,geometry},color,fill,width);return;}
      let node;
      if(g.type==='Point'){const p=project(g.coordinates);node=element('circle',{cx:p[0],cy:p[1],r:5,fill:color});}
      else if(g.type==='Polygon')node=element('path',{d:g.coordinates.map(path).join(' '),fill,stroke:color,'stroke-width':width,'fill-rule':'evenodd'});
      else if(g.type==='MultiPolygon')node=element('path',{d:g.coordinates.flatMap(p=>p.map(path)).join(' '),fill,stroke:color,'stroke-width':width,'fill-rule':'evenodd'});
      else if(g.type==='LineString')node=element('polyline',{points:g.coordinates.map(project).map(p=>p.join(',')).join(' '),fill:'none',stroke:color,'stroke-width':width});
      if(node){node.append(element('title',{},JSON.stringify(properties)));svg.append(node);}
    }
    draw({geometry:result.inputs.study_area},'#9dabb4');
    for(const f of result.spatial_artifacts.parcels.features){const active=option.state.active_project_ids.includes(f.properties.project_id);draw(f,active?'#16678d':'#8ca5b4',active?'#b6dced':'#e0e9ef');const p=project(f.geometry.coordinates[0][0]);svg.append(element('text',{x:p[0]+4,y:p[1]-7},f.properties.project_id));}
    const layer=$('layer').value;
    let note=result.inputs.data_mode==='demo_system'?'Ranh parcel từ snapshot hệ thống; công trình đề xuất và bề mặt chưa khảo sát là giả định. Sơ đồ không có nền ảnh vệ tinh.':'Vị trí và geometry của fixture synthetic; sơ đồ không có nền ảnh vệ tinh.';
    if(layer==='school'){for(const f of option.state.school_services.map.features)draw(f,'#18734d', 'none',3);note=option.state.school_services.walking_method==='osm_shortest_foot_path_with_estimated_connectors'?'Xanh: điểm trường và tuyến ngắn nhất trên OSM, đoạn nối đầu/cuối là ước tính. Tuyến access_only chưa xác nhận chỗ học; không chứng minh có vỉa hè hoặc cổng thực tế.':'Xanh: trường và tuyến đi bộ trên graph synthetic; tuyến chỉ hiển thị nhóm được phân bổ chỗ học. Khoảng cách không chứng minh có vỉa hè ngoài thực tế.';}
    if(layer==='shadow'){for(const f of option.state.shadow.map.features.filter(f=>f.properties.hour_local===Number($('shadow-hour').value)))draw(f,'#9f782a','#dfc67980',1);note='Bóng tại giờ đã chọn trên vùng nhận bóng cố định; chưa phải nhiệt độ hoặc ảnh hưởng ánh sáng cửa sổ.';}
    if(layer==='roads'){
      const run=option.state.traffic?.runs.find(r=>r.hour_local===Number($('traffic-hour').value)&&r.seed===Number($('traffic-seed').value));
      const stats=run?.edge_intervals[Number($('interval').value)]?.edges||[];
      const queues=run?.queue_intervals?.[Number($('interval').value)];
      for(const f of result.spatial_artifacts.roads?.features||[]){const data=stats.find(e=>e.edge_id===f.properties.edge_id),queue=queues?.edges.find(e=>e.edge_id===f.properties.edge_id);draw({...f,properties:{...f.properties,...data,sampled_peak_queue_m:queue?.sampled_peak_queue_m??null,queue_lanes:queues?.lanes.filter(l=>l.edge_id===f.properties.edge_id)||[]}}, data?.speed<5?'#bc3d35':'#2479a5','none',3);}
      note=run?`Mạng SUMO ${run.network_provenance?.kind==='osm_topology_with_estimated_demand'?'OSM + cổng/OD/đèn giả định':'synthetic'}, seed ${run.seed}. Đỏ: speed < 5 m/s; tooltip có hàng chờ lane lớn nhất tại mẫu 30 giây trong khoảng đã chọn. Không cộng chiều dài các lane; thiếu record không thay bằng số 0.`:'Screening chưa có dữ liệu SUMO; chạy chế độ SUMO + SWMM.';
    }
    if(layer==='drainage'||layer==='drainage_links'){
      const sample=$('drainage-sample').value;
      for(const c of option.state.drainage?.catchments||[])for(const f of (layer==='drainage'?c.map:c.link_map)?.features||[]){
        const properties={...f.properties};
        if(sample!=='event'){const i=Number(sample),key=layer==='drainage'?properties.id:properties.link_id,series=c.timeseries[layer==='drainage'?'nodes':'links'][key];for(const [metric,values] of Object.entries(series))properties[metric]=values[i];properties.minute=c.timeseries.minute[i];}
        draw({...f,properties},(sample==='event'?properties.flooding_m3:properties.flooding_m3_s)>0?'#c24734':'#257cb5');
      }
      note=option.state.drainage?`SWMM ${sample==='event'?'tổng trận mưa':`tại mẫu ${sample}`}: tooltip có depth/flow hoặc tràn nút. Không phải độ sâu ngập mặt đất hoặc vị trí cống thật.`:'Screening chưa chạy SWMM.';
    }
    $('map-note').textContent=note;
  }
  function power(state) {
    const svg=$('power');svg.replaceChildren();const max=Math.max(1,...state.hourly_power_kw,...result.baseline.hourly_power_kw);
    state.hourly_power_kw.forEach((value,h)=>{const y=145-value/max*120;const bar=element('rect',{x:25+h*19,y,width:12,height:145-y,fill:'#287a9c'});bar.append(element('title',{},`${h}h: ${number(value)} kW; nền ${number(result.baseline.hourly_power_kw[h])} kW`));svg.append(bar);if(h%3===0)svg.append(element('text',{x:25+h*19,y:164},`${h}h`));});
    svg.append(element('text',{x:25,y:15},`${number(max)} kW — tổng tại cùng giờ`));
    const panel=$('capacities');panel.replaceChildren();
    const capacityLabels={unknown:'Chưa đủ dữ liệu',within_capacity:'Trong capacity',exceeds_capacity:'Vượt capacity'};
    for(const zone of state.utility_zones)for(const check of zone.checks){const p=document.createElement('p');const unit=check.metric==='power_peak_kw'?'kW':'m³/ngày';p.textContent=`${zone.id} · ${labels[check.metric]||check.metric}: ${number(check.value)} / ${number(check.capacity)} ${unit} — ${capacityLabels[check.status]||check.status}; còn lại ${number(check.remaining_capacity)} ${unit} (${check.source_kind||'unknown'})`;p.title=check.source;if(check.status==='exceeds_capacity')p.className='bad';panel.append(p);}
  }
  function sumoResults(option) {
    const hour=Number($('traffic-hour').value),seed=Number($('traffic-seed').value);
    const pick=state=>(state.traffic?.runs||[]).find(r=>r.hour_local===hour&&r.seed===seed);
    const before=pick(result.baseline),after=pick(option.state);
    const body=$('sumo-metrics').tBodies[0];body.replaceChildren();
    if(!after){$('sumo-summary').textContent='Chưa có lượt SUMO cho giờ/seed này. Screening không chạy SUMO; chọn SUMO + SWMM rồi chạy để có thông số.';return;}
    const profile=state=>state.resolved_background?.traffic||result.context.resolved_background?.traffic;
    const count=(state,key)=>profile(state)?.[key]?.[hour]??null;
    const total=state=>{const c=count(state,'cars'),m=count(state,'motorcycles');return c==null||m==null?null:c+m;};
    const backlog=run=>run?.unfinished_vehicles==null||run?.undeparted_vehicles==null?null:run.unfinished_vehicles+run.undeparted_vehicles;
    const completed=run=>run?.completed_fraction==null?null:run.completed_fraction*100;
    const reference=result.context.system_background?.counting_reference;
    let note=`${option.title} · ${hour}h · seed ${seed}. Nền ô tô + xe máy: ${number(total(option.state))} xe/giờ; nhu cầu toàn lượt (gồm công trình): ${number(after.planned_vehicles)} xe. Xe xuất phát trong 3.600 giây, mô phỏng tới giây 4.200.`;
    if(reference){const seconds=reference.observation.duration_seconds,rate=reference.repaired_crossings*3600/seconds;note+=` Tham chiếu đã lưu: ${reference.camera_id}, ${reference.repaired_crossings} lượt/${number(seconds)} giây (${number(rate)} xe/giờ tổng các loại qua vạch). Đây là mẫu chuyển làm giả định, không phải lưu lượng đo ở khu đất.`;}
    $('sumo-summary').textContent=note;
    const rows=[
      ['Xe nền giả định: ô tô + xe máy',total(result.baseline),total(option.state),'xe/giờ'],
      ['Xe nền ô tô',count(result.baseline,'cars'),count(option.state,'cars'),'xe/giờ'],
      ['Xe nền xe máy',count(result.baseline,'motorcycles'),count(option.state,'motorcycles'),'xe/giờ'],
      ['Xe dự kiến trong giờ',before?.planned_vehicles,after.planned_vehicles,'xe'],
      ['Xe đã vào mạng',before?.departed_vehicles,after.departed_vehicles,'xe'],
      ['Xe hoàn thành',before?.completed_vehicles,after.completed_vehicles,'xe'],
      ['Xe vào mạng chưa hoàn thành',before?.unfinished_vehicles,after.unfinished_vehicles,'xe'],
      ['Xe chưa vào mạng',before?.undeparted_vehicles,after.undeparted_vehicles,'xe'],
      ['Tồn đọng cuối lượt',backlog(before),backlog(after),'xe'],
      ['Tỷ lệ hoàn thành',completed(before),completed(after),'%'],
      ['Độ trễ trung bình xe hoàn thành',before?.mean_completed_delay_seconds,after.mean_completed_delay_seconds,'s/chuyến hoàn thành'],
      ['Độ trễ xe nền hoàn thành',before?.background_completed_delay_seconds,after.background_completed_delay_seconds,'s/chuyến nền hoàn thành'],
      ['Hàng chờ tối đa',before?.max_queue_length_m,after.max_queue_length_m,'m']
    ];
    for(const [label,a,b,unit] of rows){const tr=document.createElement('tr');for(const value of [label,number(a),number(b),unit]){const td=document.createElement('td');td.textContent=value;tr.append(td);}body.append(tr);}
    const tr=document.createElement('tr');for(const text of ['Bảo toàn số xe',before?.count_balanced==null?'Chưa biết':before.count_balanced?'Đạt':'Không đạt',after.count_balanced?'Đạt':'Không đạt','']){const td=document.createElement('td');td.textContent=text;tr.append(td);}body.append(tr);
  }
  function renderVietnamRequirements(option) {
    const before=result.baseline.vietnam_planning_requirements,after=option.state.vietnam_planning_requirements;
    $('vietnam-requirements').hidden=!after;if(!after)return;
    const names={kindergarten:'Mầm non',primary:'Tiểu học',lower_secondary:'THCS'};
    const statuses={within_reference_limit:'Trong ngưỡng tham chiếu',exceeds_reference_limit:'Vượt ngưỡng tham chiếu',requires_separate_assessment:'Cần đánh giá riêng',unknown_school_level_or_inventory:'Chưa đủ dữ liệu cấp trường',outside_reference_radius:'Ngoài bán kính tham chiếu',within_reference_radius:'Trong bán kính tham chiếu'};
    $('vietnam-note').textContent=`QCVN 01:2021/BXD: sinh hoạt đô thị tối thiểu ${after.water_minimum_l_person_day} L/người/ngày; đây là mức bố trí tối thiểu, không phải số đo hoặc dự báo tiêu thụ. Nước vận hành vẫn tính trong bảng chính. Bán kính dịch vụ 500 m tách khỏi giới hạn đi bộ đang khai báo. Năng lực phục vụ và điều kiện pháp lý chưa được xác nhận.`;
    const body=$('vietnam-table').tBodies[0];body.replaceChildren();
    const rows=[['Nước sinh hoạt tối thiểu',before?.water_domestic_minimum_m3_day,after.water_domestic_minimum_m3_day,'m³/ngày; chỉ sinh hoạt, chưa gồm các nhóm nước khác']];
    for(const level of after.school_provision){const old=before?.school_provision.find(x=>x.level===level.level);rows.push([`Chỗ ${names[level.level]} cần bố trí tối thiểu`,old?.required_places,level.required_places,`chỗ; ${level.places_per_1000_residents}/1.000 dân`]);rows.push([`Đất ${names[level.level]} tối thiểu`,old?.minimum_land_m2,level.minimum_land_m2,'m²; theo số chỗ tối thiểu']);}
    for(const row of rows){const tr=document.createElement('tr');row.forEach((v,i)=>{const td=document.createElement('td');td.textContent=i===1||i===2?number(v):v;tr.append(td);});body.append(tr);}
    const detail=$('vietnam-density');detail.replaceChildren();
    for(const row of after.density_checks){const p=document.createElement('p');p.textContent=`${row.project_id} · mật độ đề xuất ${number(row.proposed_percent)}% / tham chiếu tối đa ${number(row.maximum_percent)}%: ${statuses[row.status]||row.status}. Giả định nhóm chung cư; không xác nhận được phép xây.`;if(row.status==='exceeds_reference_limit')p.className='bad';detail.append(p);}
    for(const row of after.school_radius_checks){const p=document.createElement('p');p.textContent=`${row.project_id} · ${names[row.level]}: khoảng thẳng từ tâm khu đất ${number(row.straight_line_distance_m)} m / ${row.service_radius_m} m — ${statuses[row.status]||row.status}. Trường chưa rõ cấp không được tự phân loại.`;detail.append(p);}
    const source=document.createElement('a');source.href=after.source_url;source.target='_blank';source.rel='noopener noreferrer';source.textContent='Nguồn QCVN và phạm vi áp dụng';detail.append(source);
  }
  function render() {
    const option=selected();if(!option)return;
    renderVietnamRequirements(option);
    function choices(id, items){const select=$(id),previous=select.value;select.replaceChildren(...items.map(([value,label])=>new Option(label,String(value))));if(items.some(([value])=>String(value)===previous))select.value=previous;}
    choices('traffic-seed',[...new Set((option.state.traffic?.runs||[]).filter(r=>r.hour_local===Number($('traffic-hour').value)).map(r=>r.seed))].map(seed=>[seed,String(seed)]));
    const minutes=option.state.drainage?.catchments[0]?.timeseries.minute||[];
    choices('drainage-sample',[['event','Tổng trận mưa'],...minutes.map((minute,i)=>[i,`${number(minute)} phút`])]);
    $('selected').textContent=`${option.title} · ${option.state.active_project_ids.join(' + ')||'Không kích hoạt dự án'}`;
    map(option);power(option.state);sumoResults(option);
    const manifest=result.context.source_manifest;
    const planningPanel=$('planning-review');planningPanel.replaceChildren();
    for(const review of result.context.system_background?.planning_review||[]){
      const p=document.createElement('p');p.textContent=`${review.project_id} · mã đất ${review.source_land_use_code||'chưa biết'} · ${review.source_planning_land_use||'chưa có nhãn quy hoạch'} · ${review.source_decision||'chưa có quyết định trong nguồn'} · ${review.status}. Mật độ đề xuất ${number(review.proposed_density_percent)}%; FAR ${number(review.proposed_far)}. ${review.flags.join(' ')} Chưa xác minh chỉ tiêu cho phép hoặc tính pháp lý.`;
      if(review.status==='potential_conflict')p.className='bad';planningPanel.append(p);
    }
    $('manifest-summary').textContent=manifest?`${manifest.entries.length} nguồn đầu vào được đóng băng; mã ${manifest.sha256.slice(0,16)}. ${manifest.source_kind==='mixed_demo'?'Parcel hệ thống, OSM và WorldPop kết hợp giả định demo; xem loại mạng SUMO trong kết quả. SWMM vẫn có hạ tầng tổng hợp.':'Đây là phạm vi mô hình synthetic, chưa phải độ phủ dữ liệu quan trắc.'}`:'Run cũ chưa có manifest chi tiết; tạo revision mới để xem nguồn và phạm vi.';
    const coverageBody=$('coverage').tBodies[0];coverageBody.replaceChildren();
    if(manifest){
      const modules=result.context.data_coverage.modules;
      const rows=[['Hình học','Các parcel đã khai báo','Không có inventory ngoài các parcel'],
        ['Giao thông',`${modules.traffic.edge_count} đoạn đường trong mạng tổng hợp`,modules.traffic.inside_study_area?'Chưa hiệu chỉnh bằng lưu lượng thực':'Mạng mở rộng ngoài AOI; có công bố phạm vi tổng hợp riêng'],
        ['Thoát nước','Graph cống/lưu vực được khai báo','Phần lưu vực nền chỉ có diện tích, chưa có polygon khảo sát; không có ngập 2D'],
        ['Điện/nước','Công suất và tải dùng chung theo ID vùng phục vụ','Chưa có ranh vùng phục vụ hoặc mạng tính điện áp/áp lực nước'],
        ['Trường học',modules.school.walking_network_kind==='osm_with_estimated_connectors'?'Điểm trường và mạng đi bộ OSM + đoạn nối ước tính':'Các trường/nhóm học sinh và tuyến đi bộ tổng hợp',modules.school.missing_background_demand?'Thiếu nhu cầu học sinh nền':'Chưa có tuyển sinh/vỉa hè được kiểm chứng'],
        ['Bóng đổ','Vùng nhận bóng ngoài trời cố định trong AOI',modules.shadow.fixed_context_object_count?`${modules.shadow.fixed_context_object_count} công trình/cây lân cận OSM; inventory chưa đầy đủ, chiều cao có thể giả định; không phải nhiệt độ`:'Chưa có inventory hàng xóm ngoài parcel; không phải nhiệt độ']];
      for(const values of rows){const tr=document.createElement('tr');for(const text of values){const td=document.createElement('td');td.textContent=text;tr.append(td);}coverageBody.append(tr);}
    }
    const ledger=option.state.baseline_ledger;
    const normalization=ledger?.background_normalization;
    $('background-normalization').textContent=normalization?.status==='inclusive_snapshot_normalized'?`Snapshot ${normalization.snapshot_id}: tổng dân số nền đầu vào ${number(normalization.original.residents)}; sau tách ${number(option.state.resolved_background.residents)}. Đã loại phần đóng góp của ${normalization.removed_contributions.length} parcel vật lý trước khi thêm phương án. Không trừ lại theo từng phase.`:'Dữ liệu nền được khai báo đã loại các registered parcels; không tự suy ra phần trùng từ tổng vùng.';
    const ledgerBody=$('ledger').tBodies[0];ledgerBody.replaceChildren();
    if(ledger){
      const population=ledger.population;
      $('population-ledger').textContent=`Cư dân vùng: ${number(population.baseline)} → ${number(population.final)}; thay đổi ròng ${number(population.net_delta)}. Di dời nội vùng đã khai báo: ${number(population.declared_internal_relocated)}; vào vùng ${number(population.declared_external_inflow)}, ra vùng ${number(population.declared_external_outflow)}; thay đổi ròng chưa giải thích: ${number(population.unexplained_net_change)}. Trạng thái: ${population.certainty}.`;
      $('ledger-note').textContent='Người di dời đã nằm trong số cư dân của phương án, không cộng lại dân số hoặc nhu cầu. Thay đổi ròng chưa giải thích không tự đồng nghĩa cư dân mới. '+(ledger.unresolved_existing_residents.length?`Chưa rõ nơi đến của ${number(ledger.unresolved_existing_residents.reduce((n,r)=>n+r.residents,0))} cư dân hiện hữu.`:'');
      for(const parcel of ledger.parcels)for(const [key,value] of Object.entries(parcel.loads)){
        const tr=document.createElement('tr');
        const units={residents:'người',freshwater_m3_day:'m³/ngày',wastewater_m3_day:'m³/ngày',energy_kwh_day:'kWh/ngày',person_trips_day:'chuyến người/ngày'};
        for(const text of [parcel.project_id,`${labels[key]||key} (${units[key]||''})`,number(value.baseline),number(value.accounting_removed),number(value.replacement_added),number(value.final),`${parcel.baseline_source_kind} / ${value.certainty}`]){const td=document.createElement('td');td.textContent=text;tr.append(td);}
        tr.title=parcel.baseline_source;ledgerBody.append(tr);
      }
    }else{$('population-ledger').textContent='Run cũ chưa có ledger chi tiết; tạo revision mới để đánh giá.';$('ledger-note').textContent='';}
    const body=$('metrics').tBodies[0];body.replaceChildren();
    const normalized=$('normalized').tBodies[0];normalized.replaceChildren();
    const basisLabels={floor_area_m2:'m² sàn phương án',housing_units:'căn hộ',residents:'cư dân phương án',school_places:'chỗ học',office_staff:'nhân viên văn phòng'};
    $('normalization-note').textContent=option.declared_program?'Chênh lệch so với hiện trạng chia cho quy mô toàn bộ phương án active; không chia cho dân số nền hoặc số tăng thêm. Công năng khác nhau không đồng nghĩa lợi ích bằng nhau; các tỷ lệ này không tự dùng để xếp hạng.':'Run cũ hoặc hiện trạng chưa có bảng chuẩn hóa; chạy revision mới để xem.';
    for(const row of option.normalized_comparison||[]){const tr=document.createElement('tr');const ratio=row.value==null?'Chưa biết':Number(row.value).toLocaleString('vi-VN',{maximumSignificantDigits:5});for(const text of [labels[row.metric]||row.metric,`${number(row.denominator)} ${basisLabels[row.normalization_basis]||row.normalization_basis}`,ratio,row.unit,row.comparability]){const td=document.createElement('td');td.textContent=text;tr.append(td);}tr.title=row.unavailable_reason||row.method;normalized.append(tr);}
    for(const row of [...option.comparison,...(option.traffic_comparison||[]),...(option.drainage_comparison||[])]){const tr=document.createElement('tr');for(const value of [(labels[row.metric]||row.metric)+(row.hour_local!=null?` · ${row.hour_local}h · seed ${row.seed}`:''),number(row.before),number(row.after),number(row.delta),row.unit,row.comparability]){const td=document.createElement('td');td.textContent=value;tr.append(td);}body.append(tr);}
    $('source').textContent=`Nguồn: ${result.context.source_kind} · model ${result.model_version} · context ${result.context.sha256.slice(0,16)}. Trường: ${option.state.school_services.comparability}.`;
    if(result.context.system_background)$('source').textContent+=' Parcel thật từ snapshot '+result.context.system_background.snapshot_id.slice(0,16)+(result.context.system_background.capacity_package?'. NỀN/CAPACITY GIẢ LẬP v1: occupancy và capacity không phải quan trắc; WorldPop chỉ là context.':'. Occupancy/capacity chưa biết; WorldPop là tổng vùng.')+' OD và cống còn giả lập.';
    $('ranking').textContent=result.ranking.status==='not_requested'?'Chưa chọn tiêu chí.':result.ranking.status==='insufficient_data'?'Chưa đủ chỉ số cho toàn bộ tiêu chí; chưa xếp hạng.':`Pareto theo tiêu chí đã chọn: ${result.ranking.pareto_option_ids.join(', ')}. Không mặc định một phương án tốt nhất.`;
    $('phases').replaceChildren();
    for(const marginal of result.marginal_effects){const p=document.createElement('p');const rows=marginal.rows.filter(r=>['power_peak_kw','school_unserved_students','residents'].includes(r.metric));p.textContent=`${marginal.phase_id} so với ${marginal.compared_with}: `+rows.map(r=>`${labels[r.metric]} ${number(r.delta)} ${r.unit}`).join('; ');$('phases').append(p);}
    const sampled=result.seed_analysis?.paired_deltas.filter(r=>r.option_id===option.id&&r.metric==='background_completed_delay_seconds')||[];
    const seedText=sampled.length?sampled.map(r=>`${r.hour_local}h: delta delay xe nền ${number(r.min)} đến ${number(r.max)} s; ${r.delta_stability}`).join('. '):'Chưa có kết quả nhiều seed cho giao thông.';
    const caseStability=analysisResult.uncertainty_analysis?.ranking_stability_across_cases;
    const overall=analysisResult.uncertainty_analysis?.overall_ranking_assessment;
    $('stability').textContent=seedText+(caseStability?` · Pareto qua các giả định: ${caseStability.pareto_membership_stable===true?'giữ nguyên':caseStability.pareto_membership_stable===false?'thay đổi':'chưa đủ dữ liệu'}.`:'')+(overall?` Kết luận độ ổn định: ${overall.status}; nguồn nhạy: ${overall.sensitivity_sources.join(', ')||'không thấy trong các mẫu đã chạy'}.`:'')+' Các khoảng là mẫu kịch bản đã chạy, không phải khoảng tin cậy thống kê.';
    $('audit').textContent=JSON.stringify({context_hash:result.context.sha256,conditions:result.inputs.conditions,source_note:result.inputs.source_note,service_limitations:option.state.school_services.limitations,unknown_capacity:option.state.school_services.unknown_capacity_facility_ids,shadow_limitations:option.state.shadow.limitations,unavailable:option.state.unavailable_modules,validity:result.validity,interaction_effects:result.interaction_effects,ranking:result.ranking,seed_analysis:result.seed_analysis,weight_analysis:result.weight_analysis,uncertainty_analysis:analysisResult.uncertainty_analysis,analysis_request_context_hash:analysisResult.analysis_request_context_hash,limitations:result.limitations},null,2);
  }
  function displayCase(value, preferredOption=null) {
    result=value;$('results').hidden=false;$('option').replaceChildren(new Option('Hiện trạng','baseline'));
    for(const option of [...result.options,...result.phases])$('option').append(new Option(option.title,option.id));
    $('option').value=preferredOption&&['baseline',...result.options.map(o=>o.id),...result.phases.map(o=>o.id)].includes(preferredOption)?preferredOption:result.options[0].id;
    $('traffic-hour').replaceChildren(...result.inputs.conditions.traffic_hours.map(h=>new Option(`${h}h`,String(h))));
    $('interval').replaceChildren(...Array.from({length:14},(_,i)=>new Option(`${i*5}–${(i+1)*5} phút`,String(i))));$('interval').value='4';
    $('download').href=`${base}/runs/${result.id}/artifacts`;render();
  }
  function show(value){analysisResult=value;$('assumption-case').replaceChildren(...(value.assumption_cases||[{id:'reference'}]).map(c=>new Option(c.id,c.id)));$('assumption-case').disabled=!value.assumption_cases;displayCase(value);}
  $('assumption-case').onchange=()=>{const c=analysisResult.assumption_cases?.find(c=>c.id===$('assumption-case').value);if(c)displayCase({...c.result,id:analysisResult.id,study_id:analysisResult.study_id},$('option').value);};
  async function poll(token) {
    if(token!==generation)return;
    try{
      const job=await api(`/jobs/${jobId}`);if(token!==generation)return;
      status(`Job ${job.id}\n${job.status}${job.progress?' · '+job.progress.module:''}${job.progress?.assumption_case_id?' · '+job.progress.assumption_case_id:''} · child đã xong: ${job.child_counts?.succeeded||0}`);
      if(job.status==='succeeded'){const value=await api(`/runs/${job.result_id}`);if(token!==generation)return;show(value);pending(false);status(`Hoàn thành và lưu run ${job.result_id}. Có thể mở lại bằng Job UUID hoặc tải ZIP.`);}
      else if(['failed','partial','cancelled'].includes(job.status)){pending(false);$('retry').disabled=false;status((job.error||job.status)+` · Đã giữ ${job.child_counts?.succeeded||0} child hoàn thành. Chạy tiếp dùng input job cũ; chưa có run đầy đủ để so sánh.`,job.status!=='cancelled');}
      else timer=setTimeout(()=>poll(token),1000);
    }catch(error){pending(false);status(`Không đọc được job: ${error.message}. Job có thể vẫn chạy; dùng Mở lại để kiểm tra.`,true);}
  }
  $('load-preset').onclick=preset;
  $('jump-sumo').onclick=()=>{
    if(!result){status('Chưa tải xong kết quả. Chờ job mở lại hoặc chạy SUMO + SWMM để xem bảng.');return;}
    $('input').closest('details').open=false;
    $('sumo-results').scrollIntoView({behavior:'smooth',block:'start'});
    $('sumo-results').focus({preventScroll:true});
  };
  $('input').oninput=()=>{invalidate();status('Đầu vào đã đổi; cần chạy lại để có kết quả phù hợp.');};
  $('preflight').onclick=async()=>{try{
    const ready=await api('/studies/preflight',JSON.parse($('input').value));
    const mode=$('run-mode').value;
    const work=mode==='uncertainty'?ready.uncertainty_work_estimate:ready.native_work_estimate;
    const timing=ready.runtime_estimates?.[mode];
    const duration=timing?.estimated_compute_seconds!=null
      ? `Số đo tham khảo: khoảng ${Number(timing.estimated_compute_seconds).toFixed(1)} giây tính toán; ${timing.sample_count} mẫu, khoảng quan sát ${Number(timing.min_observed_seconds).toFixed(1)}–${Number(timing.max_observed_seconds).toFixed(1)} giây. Không gồm chờ hàng đợi, lưu kết quả và tải ZIP; không phải cam kết thời gian.`
      : 'Chưa có benchmark phù hợp để ước lượng thời gian tính toán.';
    status(`Sẵn sàng: ${ready.unique_states} trạng thái; ${mode==='screening'?0:work?.sumo_runs??'?'} SUMO, ${mode==='screening'?0:work?.swmm_runs??'?'} SWMM cho chế độ đã chọn.\n${duration}\n${ready.warnings.join('\n')}`);
  }catch(error){status(error.message,true);}};
  $('run').onclick=async()=>{invalidate();const token=generation;pending(true);status('Đang lưu đầu vào và tạo job…');try{const study=await api('/studies',JSON.parse($('input').value));const job=await api(`/studies/${study.id}/runs`,{mode:$('run-mode').value,idempotency_key:crypto.randomUUID()});if(token!==generation)return;jobId=job.id;$('saved-job').value=jobId;localStorage.setItem('planning-job',jobId);await poll(token);}catch(error){pending(false);status(error.message,true);}};
  $('cancel').onclick=async()=>{try{await api(`/jobs/${jobId}/cancel`,{});status('Đã yêu cầu hủy; đang chờ worker đóng solver con.');}catch(error){status(error.message,true);}};
  $('retry').onclick=async()=>{invalidate();const token=generation;pending(true);status('Đang chạy tiếp job đã lưu…');try{const job=await api(`/jobs/${jobId}`);const study=await api(`/studies/${job.study_id}`);savedInput(study);await api(`/jobs/${jobId}/retry`,{});await poll(token);}catch(error){pending(false);status(error.message,true);}};
  $('restore').onclick=async()=>{invalidate();const token=generation;status('Đang mở lại job…');try{jobId=$('saved-job').value.trim();const job=await api(`/jobs/${jobId}`);const study=await api(`/studies/${job.study_id}`);savedInput(study);pending(true);await poll(token);}catch(error){pending(false);status(error.message,true);}};
  for(const id of ['option','layer','map-extent','shadow-hour','traffic-hour','interval','traffic-seed','drainage-sample'])$(id).onchange=render;
  let systemFeatures = [];
  const systemPrograms = new Map();
  let systemScenarios=[];
  function renderSystemScenarios(){
    $('system-scenarios').replaceChildren();
    systemScenarios.forEach((ids,i)=>{const p=document.createElement('p');p.textContent=`Phương án ${i+1}: ${ids.join(' + ')} `;const remove=document.createElement('button');remove.textContent='Bỏ';remove.onclick=()=>{systemScenarios.splice(i,1);renderSystemScenarios();};p.append(remove);$('system-scenarios').append(p);});
  }
  $('system-add-scenario').onclick=()=>{
    const ids=[...$('system-group-parcels').selectedOptions].map(o=>o.value).sort();
    if(!ids.length||systemScenarios.length>=12){status('Chọn parcel cho phương án; tối đa 12 phương án.',true);return;}
    if(systemScenarios.some(group=>JSON.stringify(group)===JSON.stringify(ids))){status('Phương án này đã được thêm.',true);return;}
    systemScenarios.push(ids);$('system-mode').value='cumulative';$('system-equal').checked=false;renderSystemScenarios();
  };
  function syncSystemSelection(){
    const ids=[...$('system-parcels').selectedOptions].map(o=>o.value);
    for(const poly of $('system-parcel-map').children)poly.setAttribute('fill',ids.includes(poly.dataset.parcel)?'#efb14a':'#cce8df');
    const previous=[...$('system-group-parcels').selectedOptions].map(o=>o.value);
    $('system-group-parcels').replaceChildren(...ids.map(id=>{const opt=new Option(id,id);opt.selected=previous.includes(id);return opt;}));
    systemScenarios=systemScenarios.filter(group=>group.every(id=>ids.includes(id)));renderSystemScenarios();
    const tbody=$('system-programs').tBodies[0];tbody.replaceChildren();
    for(const id of ids){
      const program=systemPrograms.get(id)||{housing_units:Number($('system-units').value),residents:Number($('system-residents').value),floors:Number($('system-floors').value),floor_area_m2:Number($('system-floor-area').value)};
      systemPrograms.set(id,program);const tr=document.createElement('tr'),name=document.createElement('td');name.textContent=id;tr.append(name);
      for(const key of ['housing_units','residents','floors','floor_area_m2']){const td=document.createElement('td'),input=document.createElement('input');input.type='number';input.min=key==='floor_area_m2'?'100':'1';input.value=program[key];input.setAttribute('aria-label',`${id} ${key}`);input.onchange=()=>{program[key]=Number(input.value);};td.append(input);tr.append(td);}tbody.append(tr);
    }
  }
  $('system-parcels').onchange=syncSystemSelection;
  $('system-mode').onchange=()=>{if($('system-mode').value==='cumulative')$('system-equal').checked=false;};
  api('/demo/system/counting-references').then(value=>{
    for(const reference of value.references)$('system-counting').append(new Option(`${reference.camera_id} · ${number(reference.duration_seconds)}s · prior tỷ lệ xe`,reference.id));
  }).catch(()=>{});
  api('/demo/system/traffic-default').then(value=>{
    $('system-traffic-default').textContent=`Mặc định từ counting: ${number(value.vehicles_hour)} xe/giờ cộng hai hướng; SUMO ô tô + xe máy: ${number(value.sumo_supported_vehicles_hour)} xe/giờ. Áp dụng khi không có dữ liệu riêng. Quy đổi từ ${value.sample_crossings} lượt/${number(value.sample_duration_seconds)} giây; profile ngày và chuyển sang OD là giả định, chưa hiệu chỉnh thực địa. Để trống ô đỉnh OD để dùng mức này.`;
  }).catch(()=>{});
  $('system-load').onclick=async()=>{
    try{
      const collection=await api('/demo/system/snapshots/'+$('system-snapshot').value+'/parcels');
      systemFeatures=collection.features;$('system-parcels').replaceChildren();
      for(const feature of systemFeatures){const opt=document.createElement('option');opt.value=String(feature.id);opt.textContent=`${feature.id} · ${feature.demo_area_m2.toFixed(0)} m² · ${feature.properties.phuong||''}`;$('system-parcels').append(opt);}
      const coords=systemFeatures.flatMap(f=>f.geometry.coordinates.flat());
      const xs=coords.map(p=>p[0]),ys=coords.map(p=>p[1]);const w=Math.min(...xs),e=Math.max(...xs),s=Math.min(...ys),n=Math.max(...ys);
      $('system-parcel-map').replaceChildren();
      for(const feature of systemFeatures){const poly=document.createElementNS('http://www.w3.org/2000/svg','path');poly.setAttribute('d',feature.geometry.coordinates.map(r=>r.map((p,i)=>`${i?'L':'M'}${20+(p[0]-w)/(e-w)*660},${330-(p[1]-s)/(n-s)*310}`).join(' ')+' Z').join(' '));poly.setAttribute('fill-rule','evenodd');poly.setAttribute('fill','#cce8df');poly.setAttribute('stroke','#39675d');poly.dataset.parcel=String(feature.id);poly.onclick=()=>{const opt=[...$('system-parcels').options].find(o=>o.value===String(feature.id));if(!opt.selected&&$('system-parcels').selectedOptions.length>=6){status('Ch?n t?i ?a 6 parcel.',true);return;}opt.selected=!opt.selected;syncSystemSelection();};const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=`Parcel ${feature.id}: ${feature.demo_area_m2.toFixed(0)} m²`;poly.append(title);$('system-parcel-map').append(poly);}
      $('system-info').textContent+=` · ${systemFeatures.length} parcel phù hợp demo; bấm polygon hoặc chọn danh sách.`;
    }catch(error){status(error.message,true);}
  };
  $('system-prepare').onclick=async()=>{
    try{
      const ids=[...$('system-parcels').selectedOptions].map(o=>o.value);if(!ids.length||ids.length>6)throw new Error('Chọn từ 1 đến 6 parcel.');
      // Send explicit assumptions separately; real-source mode remains the default.
      const merged=$('system-merge-parcels').checked;
      const demoOptions={background_mode:$('system-background').value,sensitivity:$('system-sensitivity').checked,sensitivity_engine:$('system-sensitivity-engine').value,planning_catalog:$('system-vietnam-catalog').checked?'qcvn_urban_2021':'none',parcel_groups:merged?[ids]:[]};
      if(merged&&systemScenarios.length)throw new Error('Bỏ các nhóm xây đồng thời trước khi gộp thành một project.');
      const equal=$('system-equal').checked&&$('system-mode').value==='site_selection';
      const prepared=await api('/demo/system/prepare',{...demoOptions,snapshot_id:$('system-snapshot').value,parcel_ids:ids,mode:$('system-mode').value,scenario_parcels:$('system-mode').value==='cumulative'?systemScenarios:[],traffic_network_mode:$('system-osm').checked?'osm_snapshot':'synthetic_corridor',counting_reference_id:$('system-counting').value||null,traffic_peak_vehicles_hour:$('system-traffic-peak').value.trim()===''?null:Number($('system-traffic-peak').value),equal_program:equal,housing_units:Number($('system-units').value),residents:Number($('system-residents').value),floors:Number($('system-floors').value),floor_area_m2:Number($('system-floor-area').value),programs:equal||merged?{}:Object.fromEntries(ids.map(id=>[id,systemPrograms.get(id)]))});
      invalidate();$('input').value=JSON.stringify(prepared.study,null,2);$('study-mode').value=prepared.study.mode==='cumulative'?'cumulative':prepared.study.projects.length===1?'single_site':'site_selection';$('preset-description').textContent=(merged?`Đã gộp ${ids.length} parcel thành một project; quy mô nhập là tổng cả nhóm. `:'')+(demoOptions.background_mode==='sourced'?'Parcel thật; dữ liệu chưa có được giữ unknown.':'Parcel thật + NỀN/CAPACITY GIẢ LẬP v1. Các ngưỡng không phải khảo sát thực tế.');status('Bước 3: kiểm tra đầu vào và số lần chạy dự kiến. Sau đó chạy Screening trước, hoặc chọn Độ nhạy.');
    }catch(error){status(error.message,true);}
  };
  api('/demo/system/snapshots').then(value=>{
    if(!value.snapshots.length)return;$('system-demo').hidden=false;
    for(const snapshot of value.snapshots){const opt=document.createElement('option');opt.value=snapshot.id;opt.textContent=`${snapshot.captured_at} · ${snapshot.parcel_count} parcel`;$('system-snapshot').append(opt);}
    const first=value.snapshots[0];$('system-info').textContent=`WorldPop: ${number(first.population)} người trong bbox (ước tính tổng vùng, không phải occupancy parcel). Snapshot ${first.id.slice(0,16)}.`;
  }).catch(()=>{});
  api('/presets').then(async value=>{
    presets=value;preset();
    const query=new URLSearchParams(window.location.search),savedJob=query.get('job');
    $('saved-job').value=savedJob||localStorage.getItem('planning-job')||'';
    if(savedJob){
      await $('restore').onclick();
      if(result){
        const option=query.get('option');
        if(option&&[...$('option').options].some(o=>o.value===option)){$('option').value=option;render();}
        const section=query.get('view')==='sumo'?$('sumo-results'):$('results');
        if(query.get('view')==='sumo')$('input').closest('details').open=false;
        section.scrollIntoView({behavior:'smooth',block:'start'});
        if(query.get('view')==='sumo')section.focus({preventScroll:true});
      }
    }
  }).catch(error=>status(error.message,true));
})();
