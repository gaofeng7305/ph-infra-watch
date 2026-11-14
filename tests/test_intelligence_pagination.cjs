const test = require('node:test');
const assert = require('node:assert/strict');
const {ClientPager,titleParts,DISPLAY_CONFIG,readDisplaySettings,truncateTitle,sortNews} = require('../site/assets/pagination.js');

const records=Array.from({length:438},(_,i)=>({id:i+1,title:`English headline ${i+1}`,sector:i%2?'energy':'telecommunications'}));

test('438 leads show 20 on page one and calculate 22 pages',()=>{
  const view=new ClientPager(20).derive(records);
  assert.equal(view.totalPages,22);assert.equal(view.start,1);assert.equal(view.end,20);assert.equal(view.rows.length,20);
});
test('last page contains the remaining 18 records',()=>{
  const pager=new ClientPager(20,22),view=pager.derive(records);
  assert.equal(view.rows.length,18);assert.equal(view.start,421);assert.equal(view.end,438);
});
test('filtering happens before page slicing and search totals are accurate',()=>{
  const view=new ClientPager(20).derive(records,x=>x.sector==='energy');
  assert.equal(view.total,219);assert.equal(view.totalPages,11);assert.ok(view.rows.every(x=>x.sector==='energy'));
});
test('filter changes and clear reset to page one and clearing restores all records',()=>{
  const pager=new ClientPager(20,9);pager.reset();assert.equal(pager.derive(records,x=>x.sector==='energy').page,1);
  pager.setPage(3);pager.reset();const cleared=pager.derive(records);assert.equal(cleared.total,438);assert.equal(cleared.page,1);
});
test('data reload clamps a page that no longer exists',()=>{
  const pager=new ClientPager(20,8),view=pager.derive(records.slice(0,25));assert.equal(view.page,2);assert.equal(view.totalPages,2);
});
test('many pages use compact ellipsis navigation',()=>{
  const last=new ClientPager(20,22).derive(records),first=new ClientPager(20,1).derive(records);
  assert.deepEqual(last.tokens,[1,'…',20,21,22]);assert.deepEqual(first.tokens,[1,2,3,'…',22]);
});
test('Chinese mode shows source and separate translation; English hides translation',()=>{
  const item={title:'Solar project expansion announced',title_zh:'太阳能项目扩建计划公布'};
  assert.deepEqual(titleParts(item,'zh'),{original:item.title,translation:item.title_zh,pending:false});
  assert.deepEqual(titleParts(item,'en'),{original:item.title,translation:'',pending:false});
});
test('Chinese originals are not translated twice and missing titles stay untranslated',()=>{
  assert.equal(titleParts({title:'菲律宾能源项目',title_zh:'菲律宾能源项目'},'zh').translation,'');
  assert.equal(titleParts({title:'Power grid update'},'zh').pending,true);
});
test('display defaults and invalid stored settings use safe defaults',()=>{
  const empty={getItem:()=>null},invalid={getItem:key=>({news_title_limit:'999',news_page_size:'x',news_show_chinese:'maybe',news_sort_order:'random'})[key]};
  assert.deepEqual(readDisplaySettings(empty),{titleLimit:30,pageSize:20,showChinese:true,sortOrder:'newest'});
  assert.deepEqual(readDisplaySettings(invalid),{titleLimit:30,pageSize:20,showChinese:true,sortOrder:'newest'});
  assert.deepEqual(DISPLAY_CONFIG.pageSizes,[10,20,30,50,100]);
});
test('Unicode truncation preserves surrogate pairs and only appends ellipsis when needed',()=>{
  assert.deepEqual(truncateTitle('A😀BC',3),{text:'A😀B...',truncated:true});
  assert.deepEqual(truncateTitle('Short',5),{text:'Short',truncated:false});
});
test('news sorting handles invalid and absent dates and keeps equal timestamps stable',()=>{
  const rows=[{id:'invalid',published_at:'bad'},{id:'one',published_at:'2026-01-01'},{id:'two',published_at:'2026-01-01'},{id:'missing'}];
  assert.deepEqual(sortNews(rows).map(x=>x.id),['one','two','invalid','missing']);
  assert.deepEqual(sortNews(rows,'oldest').map(x=>x.id),['one','two','invalid','missing']);
  const different=[{id:'old',published_at:'2025-01-01'},{id:'new',published_at:'2026-01-01'}];
  assert.deepEqual(sortNews(different).map(x=>x.id),['new','old']);
  assert.deepEqual(sortNews(different,'oldest').map(x=>x.id),['old','new']);
});
test('page size can be changed and pager corrects page boundaries',()=>{
  const pager=new ClientPager(10,8);pager.pageSize=30;
  assert.equal(pager.derive(records).totalPages,15);assert.equal(pager.derive(records.slice(0,5)).page,1);
});
