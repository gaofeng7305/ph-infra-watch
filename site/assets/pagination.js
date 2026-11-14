(() => {
  const DISPLAY_CONFIG = Object.freeze({
    titleLimits: Object.freeze([20, 30, 40, 50]),
    pageSizes: Object.freeze([10, 20, 30, 50, 100]),
    defaults: Object.freeze({ titleLimit: 30, pageSize: 20, showChinese: true, sortOrder: 'newest' })
  });
  function readDisplaySettings(storage) {
    const get = key => { try { return storage?.getItem(key); } catch { return null; } };
    const title = Number(get('news_title_limit')), size = Number(get('news_page_size'));
    const show = get('news_show_chinese'), sort = get('news_sort_order');
    return {
      titleLimit: DISPLAY_CONFIG.titleLimits.includes(title) ? title : DISPLAY_CONFIG.defaults.titleLimit,
      pageSize: DISPLAY_CONFIG.pageSizes.includes(size) ? size : DISPLAY_CONFIG.defaults.pageSize,
      showChinese: show === 'true' ? true : show === 'false' ? false : DISPLAY_CONFIG.defaults.showChinese,
      sortOrder: ['newest', 'oldest'].includes(sort) ? sort : DISPLAY_CONFIG.defaults.sortOrder
    };
  }
  function saveDisplaySetting(storage, key, value) { try { storage?.setItem(key, String(value)); } catch { /* Storage can be unavailable in private contexts. */ } }
  function truncateTitle(value, limit) {
    const chars = Array.from(String(value ?? ''));
    return chars.length > limit ? { text: chars.slice(0, limit).join('') + '...', truncated: true } : { text: chars.join(''), truncated: false };
  }
  function sortNews(records, order='newest') {
    return records.map((item,index)=>({item,index,time:Date.parse(item.published_at||'')}))
      .sort((a,b)=>{
        const av=Number.isFinite(a.time), bv=Number.isFinite(b.time);
        if(av!==bv)return av?-1:1;
        if(av&&a.time!==b.time)return order==='oldest'?a.time-b.time:b.time-a.time;
        return a.index-b.index;
      }).map(entry=>entry.item);
  }
  class ClientPager {
    constructor(pageSize=20, page=1) { this.pageSize=pageSize; this.page=page; }
    reset() { this.page=1; }
    setPage(page) { this.page=Number(page)||1; }
    derive(records, predicate=()=>true) {
      const filtered=records.filter(predicate); // Always filter before slicing.
      const total=filtered.length, totalPages=Math.max(1,Math.ceil(total/this.pageSize));
      this.page=Math.min(Math.max(1,this.page),totalPages);
      const start=total?(this.page-1)*this.pageSize+1:0, end=total?Math.min(this.page*this.pageSize,total):0;
      const visible=new Set([1,totalPages]);
      for(let n=Math.max(1,this.page-1);n<=Math.min(totalPages,this.page+1);n++) visible.add(n);
      if(this.page<=3) for(let n=1;n<=Math.min(3,totalPages);n++)visible.add(n);
      if(this.page>=totalPages-2)for(let n=Math.max(1,totalPages-2);n<=totalPages;n++)visible.add(n);
      const numbers=[...visible].sort((a,b)=>a-b), tokens=[];
      numbers.forEach((n,i)=>{if(i&&n-numbers[i-1]>1)tokens.push('…');tokens.push(n);});
      return {filtered,rows:filtered.slice((this.page-1)*this.pageSize,this.page*this.pageSize),page:this.page,totalPages,total,start,end,tokens};
    }
  }
  const hasChinese = value => /[\u3400-\u9fff]/.test(value || '');
  function titleParts(item, language) {
    const original=item.title||item.name||'Untitled', translated=typeof item.title_zh==='string'?item.title_zh.trim():'';
    if(language!=='zh'||hasChinese(original))return {original,translation:'',pending:false};
    if(translated&&translated!==original.trim())return {original,translation:translated,pending:false};
    return {original,translation:'',pending:true};
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={ClientPager,titleParts,DISPLAY_CONFIG,readDisplaySettings,saveDisplaySetting,truncateTitle,sortNews};
  else window.PHIWPager={ClientPager,titleParts,DISPLAY_CONFIG,readDisplaySettings,saveDisplaySetting,truncateTitle,sortNews};
})();
