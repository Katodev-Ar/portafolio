(function($){
'use strict';

var cfg=window.bloomReaderAnchors||{};
if(!cfg.postId||typeof window.jQuery==='undefined'){return;}

var stateKey='bloomReaderAnchorState:'+(cfg.viewerKey||'guest');
var railSizeKey='bloomReaderAnchorRailSize:'+(cfg.viewerKey||'guest');
var fontScaleKey='bloomReaderAnchorFontScale:'+(cfg.viewerKey||'guest');
var state=localStorage.getItem(stateKey)||'badges';
if(['off','badges','comments'].indexOf(state)===-1){ state='badges'; }
var groups=[];
var groupMap={};
var activeGroupId=null;
var expandedGroups={};
var composeState=null;
var railReady=false;
var railSide='right';
var booted=false;
var readerObserver=null;
var resizeObserver=null;
var scrollBadgeTimer=null;
var saveRequest=null;
var lastUiAction={key:null,ts:0};
var openCommentMenuId=null;
var lowerCommentMenuOpen=null;
var desktopClickCounter={count:0,target:null,timer:null,lastX:0,lastY:0};
var mobileTapCounter={count:0,target:null,timer:null,lastX:0,lastY:0,startX:0,startY:0,sourceTarget:null};
var readerSurfaceEventsBound=false;
var desktopGroupMenuOpen=false;
var editableShieldInstalled=false;
var railSize=readStoredRailSize();
var railResizeSyncTimer=null;
var railResizeObserver=null;
var fontScale=readStoredFontScale();
var sheetExpanded=false;
var sheetSnap='mid';
var sheetGestureState=null;

function esc(text){
  return $('<div>').text(text==null?'':String(text)).html();
}

function clamp(value,min,max){
  return Math.max(min, Math.min(max, value));
}

function readStoredRailSize(){
  try{
    var raw=localStorage.getItem(railSizeKey)||'';
    if(!raw){ return {width:null,height:null}; }
    var parsed=JSON.parse(raw);
    return {
      width: parsed && Number(parsed.width)>0 ? Math.round(Number(parsed.width)) : null,
      height: parsed && Number(parsed.height)>0 ? Math.round(Number(parsed.height)) : null
    };
  }catch(err){
    return {width:null,height:null};
  }
}

function storeRailSize(width,height){
  railSize={
    width: Number(width)>0 ? Math.round(Number(width)) : null,
    height: Number(height)>0 ? Math.round(Number(height)) : null
  };
  try{
    if(!railSize.width && !railSize.height){
      localStorage.removeItem(railSizeKey);
    }else{
      localStorage.setItem(railSizeKey, JSON.stringify(railSize));
    }
  }catch(err){}
}

function syncRailSizeFromElement(){
  var rail=$('#lrs-anchor-rail')[0];
  if(!rail || !railReady){ return; }
  var rect=rail.getBoundingClientRect();
  if(rect.width<360 || rect.height<260){ return; }
  storeRailSize(rect.width, rect.height);
  applyPanelScale();
}

function bindRailResizeObserver(){
  if(railResizeObserver || !window.ResizeObserver){ return; }
  var rail=$('#lrs-anchor-rail')[0];
  if(!rail){ return; }
  railResizeObserver=new ResizeObserver(function(){
    window.clearTimeout(railResizeSyncTimer);
    railResizeSyncTimer=window.setTimeout(syncRailSizeFromElement,120);
  });
  railResizeObserver.observe(rail);
}

function readStoredFontScale(){
  try{
    var stored=localStorage.getItem(fontScaleKey);
    if(stored==null || stored===''){ return 1.15; }
    var raw=parseFloat(stored||'1.15');
    if(!raw || !isFinite(raw)){ return 1.15; }
    return clamp(raw, 0.9, 3.2);
  }catch(err){
    return 1.15;
  }
}

function storeFontScale(value){
  fontScale=clamp(Number(value)||1, 0.9, 3.2);
  try{
    localStorage.setItem(fontScaleKey, String(fontScale));
  }catch(err){}
}

function applyFontScale(){
  var value=String(fontScale||1);
  $('#lrs-anchor-rail, #lrs-anchor-sheet .lrs-anchor-sheet-panel').css('--lrs-anchor-font-scale', value);
}

function panelScaleForWidth(width){
  var numeric=Number(width)||0;
  if(!numeric){ return 1; }
  return 1;
}

function applyPanelScale(){
  var $rail=$('#lrs-anchor-rail');
  if($rail.length){
    $rail.css('--lrs-anchor-panel-scale', String(panelScaleForWidth($rail.outerWidth())));
  }
  var $sheet=$('#lrs-anchor-sheet .lrs-anchor-sheet-panel');
  if($sheet.length){
    $sheet.css('--lrs-anchor-panel-scale', String(panelScaleForWidth($sheet.outerWidth())));
  }
}

function mobileSheetMidHeightPx(){
  var viewport=window.innerHeight||0;
  if(!viewport){ return 420; }
  return Math.round(Math.max(300, Math.min(viewport-74, viewport*0.58)));
}

function mobileSheetFullHeightPx(){
  var viewport=window.innerHeight||0;
  if(!viewport){ return 720; }
  return Math.round(Math.max(420, Math.min(viewport-10, viewport*0.92)));
}

function activeSheetHeightPx(){
  if(sheetSnap==='full'){ return mobileSheetFullHeightPx(); }
  return mobileSheetMidHeightPx();
}

function applySheetHeight(height){
  var numeric=Math.round(Number(height)||0);
  if(!numeric){ return; }
  $('#lrs-anchor-sheet').css('--lrs-sheet-height', numeric+'px');
}

function clearSheetHeight(){
  $('#lrs-anchor-sheet').css('--lrs-sheet-height','');
}

function setSheetSnap(snap){
  var next=(snap==='full' || snap==='mid' || snap==='closed') ? snap : 'mid';
  sheetSnap=next;
  sheetExpanded=(next==='full');
  $('#lrs-anchor-sheet')
    .toggleClass('is-closed', next==='closed')
    .toggleClass('is-full', next==='full')
    .toggleClass('is-mid', next==='mid')
    .toggleClass('is-expanded', next==='full');
  if(next==='closed'){
    clearSheetHeight();
  }else{
    applySheetHeight(activeSheetHeightPx());
  }
}

function setSheetExpanded(expanded){
  setSheetSnap(expanded ? 'full' : 'mid');
}

function bindSheetGestures(){
  if($('#lrs-anchor-sheet').attr('data-lrsSheetGestures')){ return; }
  $('#lrs-anchor-sheet').attr('data-lrsSheetGestures','1');
  $(document).on('touchstart pointerdown', '.lrs-anchor-sheet-handle, #lrs-anchor-sheet .lrs-anchor-rail-head', function(e){
    if(window.innerWidth>768){ return; }
    if(!$('#lrs-anchor-sheet').hasClass('is-open')){ return; }
    if(isEditableZoneTarget(e.target)){ return; }
    if($(e.target).closest('button,a,input,textarea,select,label').length){ return; }
    var original=e.originalEvent || e;
    var touch=(original.touches && original.touches[0]) || (original.changedTouches && original.changedTouches[0]) || original;
    if(!touch){ return; }
    var panel=$('#lrs-anchor-sheet .lrs-anchor-sheet-panel')[0];
    sheetGestureState={
      startY:touch.clientY,
      lastY:touch.clientY,
      startSnap:sheetSnap,
      startHeight:panel ? Math.round(panel.getBoundingClientRect().height) : activeSheetHeightPx()
    };
    $('#lrs-anchor-sheet').addClass('is-dragging');
  });
  $(document).on('touchmove pointermove', '.lrs-anchor-sheet-handle, #lrs-anchor-sheet .lrs-anchor-rail-head', function(e){
    if(window.innerWidth>768 || !sheetGestureState){ return; }
    var original=e.originalEvent || e;
    var touch=(original.touches && original.touches[0]) || (original.changedTouches && original.changedTouches[0]) || original;
    if(!touch){ return; }
    sheetGestureState.lastY=touch.clientY;
    var delta=sheetGestureState.startY-touch.clientY;
    var nextHeight=clamp(sheetGestureState.startHeight+delta, 160, mobileSheetFullHeightPx());
    applySheetHeight(nextHeight);
    if(e.cancelable){ e.preventDefault(); }
  });
  $(document).on('touchend pointerup pointercancel', '.lrs-anchor-sheet-handle, #lrs-anchor-sheet .lrs-anchor-rail-head', function(){
    if(window.innerWidth>768 || !sheetGestureState){
      sheetGestureState=null;
      $('#lrs-anchor-sheet').removeClass('is-dragging');
      return;
    }
    var delta=sheetGestureState.lastY-sheetGestureState.startY;
    var startSnap=sheetGestureState.startSnap||sheetSnap||'mid';
    var draggedHeight=clamp(sheetGestureState.startHeight-delta, 160, mobileSheetFullHeightPx());
    var midHeight=mobileSheetMidHeightPx();
    var fullHeight=mobileSheetFullHeightPx();
    sheetGestureState=null;
    $('#lrs-anchor-sheet').removeClass('is-dragging');
    if(delta>=76 && (startSnap==='mid' || draggedHeight < (midHeight*0.72))){
      setState('badges');
      return;
    }
    if(delta>=76 && startSnap==='full'){
      setSheetSnap('mid');
      return;
    }
    if(delta<=-56){
      setSheetSnap('full');
      return;
    }
    var midpoint=(midHeight+fullHeight)/2;
    if(draggedHeight>=midpoint){
      setSheetSnap('full');
    }else{
      setSheetSnap('mid');
    }
  });
}

function visibleComposeTextarea(){
  var $textarea=$('#lrs-anchor-sheet.is-open #lrs-anchor-compose-text, #lrs-anchor-rail #lrs-anchor-compose-text').filter(':visible').first();
  if($textarea.length){ return $textarea; }
  return $('#lrs-anchor-compose-text:visible').first();
}

function stashComposeDraft(){
  if(!composeState){ return; }
  var $textarea=visibleComposeTextarea();
  if(!$textarea.length){ return; }
  composeState.draft=$textarea.val()||'';
}

function syncComposeDraftFromField(field){
  if(!composeState || !field){ return; }
  composeState.draft=$(field).val()||'';
}

function insertTextAroundSelection(before, after, placeholder){
  var $textarea=visibleComposeTextarea();
  if(!$textarea.length){ return; }
  var el=$textarea[0];
  var value=el.value||'';
  var start=el.selectionStart||0;
  var end=el.selectionEnd||0;
  var selected=value.slice(start,end) || (placeholder||'');
  var next=value.slice(0,start)+before+selected+after+value.slice(end);
  el.value=next;
  var cursor=start+before.length+selected.length+after.length;
  $textarea.val(next).focus();
  el.selectionStart=cursor;
  el.selectionEnd=cursor;
  if(composeState){ composeState.draft=next; }
}

function insertPlainTextAtCursor(text){
  var $textarea=visibleComposeTextarea();
  if(!$textarea.length){ return; }
  var el=$textarea[0];
  var value=el.value||'';
  var start=el.selectionStart||0;
  var end=el.selectionEnd||0;
  var next=value.slice(0,start)+text+value.slice(end);
  el.value=next;
  var cursor=start+text.length;
  $textarea.val(next).focus();
  el.selectionStart=cursor;
  el.selectionEnd=cursor;
  if(composeState){ composeState.draft=next; }
}

function promptAndInsert(tag, promptText){
  var url=window.prompt(promptText||'');
  if(!url){ return; }
  insertPlainTextAtCursor('['+tag+']'+url+'[/'+tag+']');
}

function lowerFormTextarea(){
  return $('#comments.comments-area #comment').first();
}

function insertLowerTextAroundSelection(before, after, placeholder){
  var $textarea=lowerFormTextarea();
  if(!$textarea.length){ return; }
  var el=$textarea[0];
  var value=el.value||'';
  var start=el.selectionStart||0;
  var end=el.selectionEnd||0;
  var selected=value.slice(start,end) || (placeholder||'');
  var next=value.slice(0,start)+before+selected+after+value.slice(end);
  el.value=next;
  var cursor=start+before.length+selected.length+after.length;
  $textarea.val(next).focus();
  el.selectionStart=cursor;
  el.selectionEnd=cursor;
}

function insertLowerPlainTextAtCursor(text){
  var $textarea=lowerFormTextarea();
  if(!$textarea.length){ return; }
  var el=$textarea[0];
  var value=el.value||'';
  var start=el.selectionStart||0;
  var end=el.selectionEnd||0;
  var next=value.slice(0,start)+text+value.slice(end);
  el.value=next;
  var cursor=start+text.length;
  $textarea.val(next).focus();
  el.selectionStart=cursor;
  el.selectionEnd=cursor;
}

function lowerPromptAndInsert(tag, promptText){
  var url=window.prompt(promptText||'');
  if(!url){ return; }
  insertLowerPlainTextAtCursor('['+tag+']'+url+'[/'+tag+']');
}

function uploadToolbarButtons($scope, disabled){
  $scope.find('.lrs-anchor-tool[data-compose-action="image"], .lrs-anchor-tool[data-compose-action="gif"], .lrs-bottom-tool[data-compose-action="image"], .lrs-bottom-tool[data-compose-action="gif"]').prop('disabled', !!disabled);
}

function uploadCommentMedia(kind, scope){
  if(!cfg.isLoggedIn){
    window.location.href=cfg.loginUrl;
    return;
  }
  var accept=(kind==='gif') ? 'image/gif' : 'image/jpeg,image/png,image/webp';
  var input=document.createElement('input');
  input.type='file';
  input.accept=accept;
  input.style.position='fixed';
  input.style.left='-9999px';
  document.body.appendChild(input);
  input.addEventListener('change', function(){
    var file=input.files && input.files[0];
    document.body.removeChild(input);
    if(!file){ return; }
    var formData=new FormData();
    formData.append('action','bloom_reader_anchor_upload');
    formData.append('nonce',cfg.saveNonce||cfg.nonce);
    formData.append('kind',kind);
    formData.append('file',file);
    uploadToolbarButtons($(document.body), true);
    $.ajax({
      url:cfg.ajaxUrl,
      method:'POST',
      data:formData,
      processData:false,
      contentType:false,
      timeout:45000
    }).done(function(res){
      if(!res || !res.success || !res.data || !res.data.tag){
        return;
      }
      if(res.data.save_nonce){
        cfg.saveNonce=res.data.save_nonce;
      }
      if(scope==='lower'){
        insertLowerPlainTextAtCursor(res.data.tag);
      }else{
        insertPlainTextAtCursor(res.data.tag);
      }
    }).fail(function(xhr){
      var message=(xhr.responseJSON && xhr.responseJSON.data && xhr.responseJSON.data.message) || cfg.strings.uploadFailed || cfg.strings.genericError;
      window.alert(message);
    }).always(function(){
      uploadToolbarButtons($(document.body), false);
    });
  }, {once:true});
  input.click();
}

function hasCommentMode(){
  return state==='comments' || state==='badges';
}

function acceptUiAction(key){
  var now=Date.now();
  if(lastUiAction.key===key && (now-lastUiAction.ts)<420){
    return false;
  }
  lastUiAction={key:key,ts:now};
  return true;
}

function setState(next){
  state=next;
  localStorage.setItem(stateKey,state);
  updateCommentButton();
  renderBadges();
  updateRailLayout();
  if(state==='off'){
    closeSheet();
    activeGroupId=null;
    composeState=null;
  }
  renderActiveSurface();
}

function cycleState(){
  if(state==='off'){ setState('comments'); return; }
  if(state==='badges'){ setState('comments'); return; }
  setState('off');
}

function readerImages(){
  return $('#readerarea img.ts-main-image');
}

function readerArea(){
  return $('#readerarea');
}

function ensureOverlay(){
  var $reader=readerArea();
  if(!$reader.length){ return $(); }
  var $overlay=$reader.children('.lrs-anchor-overlay');
  if(!$overlay.length){
    $overlay=$('<div class="lrs-anchor-overlay" aria-hidden="true"></div>');
    $reader.append($overlay);
  }
  return $overlay;
}

function isUiTarget(target){
  return !!$(target).closest('#lrs-anchor-rail,#lrs-anchor-sheet,#lrs-navbar,#lrs-btn-comments,#bcm-reopen,#comments.comments-area,.lrs-anchor-badge,textarea,input,button,select,a,label').length;
}

function isEditableZoneTarget(target){
  return !!$(target).closest(
    '#lrs-anchor-rail textarea,'+
    '#lrs-anchor-rail input,'+
    '#lrs-anchor-sheet textarea,'+
    '#lrs-anchor-sheet input,'+
    '#comments.comments-area textarea,'+
    '#comments.comments-area input,'+
    '#comments.comments-area [contenteditable="true"],'+
    '.lrs-anchor-composer,'+
    '.lrs-bottom-compose-toolbar-wrap'
  ).length;
}

function ensureCommentsButton(){
  var $navbar=$('#lrs-navbar');
  if(!$navbar.length||$('#lrs-btn-comments').length){ return; }
  var icon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 18h7l4 3v-3h1a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H5A2 2 0 0 0 3 7v9a2 2 0 0 0 2 2h2z"/></svg>';
  var $btn=$('<button type="button" id="lrs-btn-comments" class="lrs-nav-btn" />')
    .append('<span class="lrs-anchor-btn-icon">'+icon+'</span>')
    .append('<span class="lrs-anchor-btn-count">0</span>');
  var $sep=$('<div class="lrs-sep lrs-anchor-sep"></div>');
  var $home=$('#lrs-btn-home');
  var $prev=$('#lrs-btn-prev');
  if($home.length && $prev.length){
    var $homeSep=$home.next('.lrs-sep');
    if($homeSep.length){
      $homeSep.after($btn);
      $btn.after($sep);
      $sep.after($prev);
    }else{
      $home.after($btn);
      $btn.after($sep);
      $sep.after($prev);
    }
  }else{
    var $chapters=$('#lrs-btn-chapters');
    if($chapters.length){
      $chapters.before($sep).before($btn);
    }else{
      $navbar.append($btn);
    }
  }
  $(document).on('click touchend pointerup','#lrs-btn-comments',function(e){
    e.preventDefault();
    e.stopPropagation();
    if(e.stopImmediatePropagation){ e.stopImmediatePropagation(); }
    if(!acceptUiAction('toggle-comments')){ return; }
    cycleState();
  });
  updateCommentButton();
}

function updateCommentButton(){
  var $btn=$('#lrs-btn-comments');
  if(!$btn.length){ return; }
  $btn.removeClass('is-off is-badges is-comments').addClass('is-'+state);
  $btn.attr('title',cfg.strings.buttonTitle+' - '+state);
  var total=0;
  groups.forEach(function(group){ total+=Number(group.count||0); });
  $btn.toggleClass('is-empty', total<=0);
  $btn.find('.lrs-anchor-btn-count').text(total>0 ? total : '');
}

function findImageForGroup(group){
  if(!group){ return $(); }
  var $match=$();
  readerImages().each(function(){
    var $img=$(this);
    var sameKey=group.image_key && imageKeyFor($img) && String(group.image_key)===String(imageKeyFor($img));
    if(sameKey || Number(group.image_index)===Number(imageIndexFor($img))){
      $match=$img;
      return false;
    }
  });
  return $match;
}

function ensureRail(){
  if($('#lrs-anchor-rail').length){ return; }
  $('body').append(
    $('<aside id="lrs-anchor-rail" aria-live="polite" />')
      .append(
        $('<div class="lrs-anchor-rail-head" />')
          .append(
            $('<div />')
              .append('<div class="lrs-anchor-rail-title">'+esc(cfg.strings.commentsTitle)+'</div>')
              .append('<div class="lrs-anchor-rail-sub">Anclados al capitulo</div>')
          )
          .append('<div class="lrs-anchor-rail-head-actions"><div class="lrs-anchor-font-controls" aria-label="Tamano del texto"><button type="button" class="lrs-anchor-font-btn" data-font-scale="-1" aria-label="Reducir texto">A-</button><button type="button" class="lrs-anchor-font-btn" data-font-scale="1" aria-label="Aumentar texto">A+</button></div><span class="lrs-anchor-group-count">0</span><button type="button" class="lrs-nav-btn" id="lrs-anchor-rail-close" aria-label="Cerrar panel de comentarios">×</button></div>')
      )
      .append('<div class="lrs-anchor-rail-body"></div>')
  );
  bindRailResizeObserver();
  applyFontScale();
}

function ensureSheet(){
  if($('#lrs-anchor-sheet').length){ return; }
  $('body').append(
    $('<div id="lrs-anchor-sheet" />')
      .append('<div class="lrs-anchor-sheet-backdrop"></div>')
      .append(
        $('<div class="lrs-anchor-sheet-panel" />')
          .append('<div class="lrs-anchor-sheet-handle" aria-hidden="true"></div>')
          .append(
            $('<div class="lrs-anchor-rail-head" />')
              .append(
                $('<div />')
                  .append('<div class="lrs-anchor-rail-title">'+esc(cfg.strings.commentsTitle)+'</div>')
                  .append('<div class="lrs-anchor-rail-sub">Anclados al capitulo</div>')
              )
              .append('<button type="button" class="lrs-nav-btn" id="lrs-anchor-sheet-close" aria-label="Cerrar comentarios">×</button>')
          )
          .append('<div class="lrs-anchor-rail-body"></div>')
      )
  );
  applyFontScale();
  bindSheetGestures();
  $(document).on('click touchend pointerup','.lrs-anchor-sheet-backdrop,#lrs-anchor-sheet-close,#lrs-anchor-rail-close',function(e){
    if($(e.target).hasClass('lrs-anchor-sheet-backdrop') && window.innerWidth<=768){
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    if(e.stopImmediatePropagation){ e.stopImmediatePropagation(); }
    if(!acceptUiAction('close-comments')){ return; }
    setState('badges');
  });
}

function openSheet(snap){
  if(window.innerWidth<=768){
    setSheetSnap(snap||((sheetSnap&&sheetSnap!=='closed')?sheetSnap:'mid'));
  }
  $('#lrs-anchor-sheet').addClass('is-open');
  applyPanelScale();
}

function closeSheet(){
  $('#lrs-anchor-sheet').removeClass('is-dragging');
  $('#lrs-anchor-sheet').removeClass('is-open');
  setSheetSnap('closed');
}

function bindResizeObserver(){
  if(typeof ResizeObserver==='undefined'){ return; }
  if(!resizeObserver){
    resizeObserver=new ResizeObserver(function(entries){
      entries.forEach(function(entry){
        if(!$(entry.target).is('img.ts-main-image')){ return; }
        renderBadges();
        updateRailLayout();
      });
    });
  }
  readerImages().each(function(){
    if(!this.dataset.lrsResizeObserved){
      resizeObserver.observe(this);
      this.dataset.lrsResizeObserved='1';
    }
  });
}

function prepareReaderImages(){
  readerImages().each(function(){
    var $img=$(this);
    if(!$img.data('lrsLoadBound')){
      $img.on('load.lrsAnchor', function(){
        renderBadges();
        updateRailLayout();
      });
      $img.data('lrsLoadBound', true);
    }
  });
  ensureOverlay();
  bindResizeObserver();
}

function imageIndexFor($img){
  var idx=parseInt($img.attr('data-index'),10);
  if(!isNaN(idx)){ return idx; }
  return readerImages().index($img);
}

function imageKeyFor($img){
  var src=$img.attr('data-src')||$img.attr('src')||$img.prop('currentSrc')||'';
  if(!src){ return ''; }
  try{
    var url=new URL(src,window.location.href);
    var pathname=url.pathname||'';
    return pathname.split('/').pop()||src;
  }catch(err){
    var parts=src.split('/');
    return parts[parts.length-1]||src;
  }
}

function percentCoords($img, clientX, clientY){
  var rect=$img[0].getBoundingClientRect();
  if(!rect.width||!rect.height){ return null; }
  var x=((clientX-rect.left)/rect.width)*100;
  var y=((clientY-rect.top)/rect.height)*100;
  x=Math.max(2,Math.min(98,x));
  y=Math.max(2,Math.min(98,y));
  return {x:x,y:y};
}

function resolveReaderImage(target, clientX, clientY){
  if(target && typeof target.closest==='function'){
    var direct=target.closest('img.ts-main-image');
    if(direct){ return direct; }
  }
  if(typeof document.elementsFromPoint==='function' && clientX!=null && clientY!=null){
    var stack=document.elementsFromPoint(clientX, clientY) || [];
    for(var i=0;i<stack.length;i++){
      var el=stack[i];
      if(!el){ continue; }
      if(el.matches && el.matches('img.ts-main-image')){ return el; }
      if(typeof el.closest==='function'){
        var nested=el.closest('img.ts-main-image');
        if(nested){ return nested; }
      }
    }
  }
  var fallback=readerImages().filter(function(){
    var rect=this.getBoundingClientRect();
    return clientX>=rect.left && clientX<=rect.right && clientY>=rect.top && clientY<=rect.bottom;
  }).first();
  return fallback.length ? fallback[0] : null;
}

function groupDistance(group,imageIndex,x,y){
  if(Number(group.image_index)!==Number(imageIndex)){ return Infinity; }
  var dx=Number(group.x_pct)-x;
  var dy=Number(group.y_pct)-y;
  return Math.sqrt(dx*dx+dy*dy);
}

function findNearbyGroup(imageIndex,x,y){
  var nearest=null;
  var best=Infinity;
  groups.forEach(function(group){
    var dist=groupDistance(group,imageIndex,x,y);
    if(dist<best){
      best=dist;
      nearest=group;
    }
  });
  return best<=6 ? nearest : null;
}

function fetchGroups(cb){
  $.post(cfg.ajaxUrl,{
    action:'bloom_reader_anchor_fetch',
    nonce:cfg.nonce,
    post_id:cfg.postId
  }).done(function(res){
    if(!res||!res.success||!res.data){ return; }
    if(res.data.save_nonce){ cfg.saveNonce=res.data.save_nonce; }
    groups=res.data.groups||[];
    groupMap={};
    groups.forEach(function(group){ groupMap[group.group]=group; });
    if(activeGroupId && !groupMap[activeGroupId]){
      activeGroupId=null;
    }
    if(!activeGroupId && groups.length===1){
      activeGroupId=groups[0].group;
    }
    updateCommentButton();
    renderBadges();
    updateRailLayout();
    renderActiveSurface();
    if(typeof cb==='function'){ cb(res.data); }
  });
}

function badgePositionForImage($img,group){
  var $reader=readerArea();
  if(!$reader.length||!$img.length){ return null; }
  var readerRect=$reader[0].getBoundingClientRect();
  var rect=$img[0].getBoundingClientRect();
  if(!rect.width||!rect.height){ return null; }
  var imgRightWithinReader=(rect.right-readerRect.left);
  var gutterRight=Math.max(0, readerRect.width-imgRightWithinReader);
  var badgeOffset=(gutterRight>=34) ? Math.min(gutterRight-10, 22) : -18;
  return {
    left:imgRightWithinReader+badgeOffset,
    top:(rect.top-readerRect.top)+(rect.height*(Number(group.y_pct||0)/100))
  };
}

function renderBadges(){
  prepareReaderImages();
  var $overlay=ensureOverlay();
  if(!$overlay.length){ return; }
  $overlay.empty();
  var hideAll=(state==='off');
  groups.forEach(function(group){
    var $img=findImageForGroup(group);
    if(!$img||!$img.length){ return; }
    var position=badgePositionForImage($img,group);
    if(!position){ return; }
    var $badge=$('<button type="button" class="lrs-anchor-badge" />')
      .attr('data-group',group.group)
      .attr('aria-label','Abrir hilo con '+group.count+' comentarios')
      .text(String(group.count))
      .css({left:position.left+'px', top:position.top+'px'});
    if(hideAll){ $badge.addClass('is-hidden'); }
    if(activeGroupId===group.group){ $badge.addClass('is-active'); }
    $overlay.append($badge);
  });
}

function railLayoutForCurrentLayout(){
  if(window.innerWidth<=768){ return {ready:false,width:0,side:'right',rect:null}; }
  var img=readerImages().first();
  if(!img.length){ return {ready:false,width:0,side:'right',rect:null}; }
  var rect=img[0].getBoundingClientRect();
  var side='right';
  var desired=Math.round(window.innerWidth*0.34);
  desired=Math.max(430, Math.min(620, desired));
  var viewportMax=Math.max(0, window.innerWidth-24);
  var overlapAllowance=Math.min(Math.max(rect.width*0.22, 120), 220);
  var maxWidth=Math.min(980, Math.max(540, Math.min(viewportMax, desired+overlapAllowance)));
  var width=Math.min(desired, maxWidth);
  return {
    ready: width>=380,
    width: width,
    maxWidth: maxWidth,
    side: side,
    rect: rect
  };
}

function updateRailLayout(){
  ensureRail();
  var layout=railLayoutForCurrentLayout();
  if(state!=='comments' || !layout.ready){
    $('body').removeClass('lrs-anchor-rail-ready');
    $('#lrs-anchor-rail').removeClass('is-left is-right');
    railReady=false;
    railSide='right';
    return;
  }
  railSide=layout.side;
  var width=layout.width;
  if(railSize.width){
    width=Math.max(width, Math.min(layout.maxWidth||layout.width, railSize.width));
  }
  var top=84;
  var navbar=document.getElementById('lrs-navbar');
  var availableHeight=window.innerHeight-96;
  if(navbar){
    var navRect=navbar.getBoundingClientRect();
    if(navRect.width>0 && navRect.height>0){
      availableHeight=Math.min(availableHeight, Math.max(280, Math.floor(navRect.top-top-16)));
    }
  }
  var height=railSize.height ? Math.max(320, Math.min(availableHeight, railSize.height)) : Math.max(420, Math.min(availableHeight, Math.round(window.innerHeight*0.72)));
  var css={width:width+'px', left:'auto', right:'auto', top:top+'px', height:height+'px'};
  if(layout.side==='right'){
    css.left=Math.max(12, Math.min(layout.rect.right+16, window.innerWidth-width-12))+'px';
  }else{
    css.left=Math.max(12, Math.min(layout.rect.left-width-16, window.innerWidth-width-12))+'px';
  }
  $('#lrs-anchor-rail').css(css).removeClass('is-left is-right').addClass('is-'+layout.side);
  $('body').addClass('lrs-anchor-rail-ready');
  railReady=true;
  applyPanelScale();
}

function previewComments(comments,expanded){
  if(expanded||comments.length<=3){ return comments; }
  return comments.slice(-3);
}

function menuDotsIconHtml(){
  return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="5" r="1.8"></circle><circle cx="12" cy="12" r="1.8"></circle><circle cx="12" cy="19" r="1.8"></circle></svg>';
}

function likeButtonHtml(comment){
  if(!comment){ return ''; }
  var liked=!!comment.liked;
  var count=Number(comment.like_count||0);
  var label=liked ? (cfg.strings.liked||'Te gusta') : (cfg.strings.like||'Me gusta');
  return '<button type="button" class="lrs-anchor-like'+(liked?' is-liked':'')+'" data-comment-id="'+comment.id+'" data-liked="'+(liked?1:0)+'">'+
    '<span class="lrs-anchor-like-heart" aria-hidden="true">❤</span>'+
    '<span class="lrs-anchor-like-label">'+esc(label)+'</span>'+
    '<span class="lrs-anchor-like-count">'+esc(String(count))+'</span>'+
  '</button>';
}

function threadHtml(group){
  if(!group){
    return '<div class="lrs-anchor-blank">'+esc(window.innerWidth<=768?cfg.strings.emptyHintMobile:cfg.strings.emptyHint)+'</div>';
  }
  var expanded=!!expandedGroups[group.group];
  var list=previewComments(group.comments||[],expanded);
  var root=list.find(function(comment){ return !Number(comment.parent_id||0); }) || list[0];
  var replies=list.filter(function(comment){ return root ? comment.id!==root.id : true; });
  var inlineReply=(composeState && composeState.mode==='reply' && composeState.inline && composeState.anchor_group===group.group) ? composeState : null;
  function inlineComposerIfNeeded(commentId){
    if(!inlineReply){ return ''; }
    var targetId=Number(inlineReply.parent_id||0) || (root ? Number(root.id||0) : 0);
    if(Number(commentId)!==targetId){ return ''; }
    return '<div class="lrs-anchor-inline-composer">'+composerHtml(inlineReply)+'</div>';
  }
  function commentMenuHtml(comment){
    var items='';
    if(cfg.canModerate){
      items+='<button type="button" class="lrs-anchor-comment-menu-action" data-menu-action="moderate" data-comment-id="'+comment.id+'">'+esc(cfg.strings.moderateComment||'Moderar comentario')+'</button>';
    }
    if(cfg.canModerate || Number(comment.author_user_id||0)===Number(cfg.currentUserId||0)){
      items+='<button type="button" class="lrs-anchor-comment-menu-action" data-menu-action="delete-comment" data-comment-id="'+comment.id+'">'+esc(cfg.strings.deleteComment||'Eliminar comentario')+'</button>';
    }
    items+='<button type="button" class="lrs-anchor-comment-menu-action" data-menu-action="copy-comment" data-comment-id="'+comment.id+'">'+esc(cfg.strings.copyComment||'Copiar comentario')+'</button>';
    items+='<button type="button" class="lrs-anchor-comment-menu-action" data-menu-action="copy-user-name" data-comment-id="'+comment.id+'">'+esc(cfg.strings.copyUserName||'Copiar nombre de usuario')+'</button>';
    items+='<button type="button" class="lrs-anchor-comment-menu-action" data-menu-action="copy-comment-id" data-comment-id="'+comment.id+'">'+esc(cfg.strings.copyCommentId||'Copiar ID de comentario')+'</button>';
    if(Number(comment.author_user_id||0)>0){
      items+='<button type="button" class="lrs-anchor-comment-menu-action" data-menu-action="copy-user-id" data-comment-id="'+comment.id+'">'+esc(cfg.strings.copyUserId||'Copiar ID de usuario')+'</button>';
    }
    if(cfg.isLoggedIn && Number(comment.author_user_id||0)!==Number(cfg.currentUserId||0)){
      if(comment.reported){
        items+='<button type="button" class="lrs-anchor-comment-menu-action is-disabled" disabled>'+esc(cfg.strings.reported||'Reportado')+'</button>';
      }else{
        items+='<button type="button" class="lrs-anchor-comment-menu-action" data-menu-action="report" data-comment-id="'+comment.id+'">'+esc(cfg.strings.report||'Reportar')+'</button>';
      }
    }
    return '<div class="lrs-anchor-comment-menu'+(Number(openCommentMenuId)===Number(comment.id)?' is-open':'')+'">'+
      '<button type="button" class="lrs-anchor-comment-menu-toggle" data-comment-id="'+comment.id+'" aria-label="Mas opciones">⋮</button>'+
      '<div class="lrs-anchor-comment-menu-panel">'+items+'</div>'+
    '</div>';
  }
  var html='<div class="lrs-anchor-thread">';
  if(root){
    html+='<article class="lrs-anchor-comment">';
    html+='<div class="lrs-anchor-comment-head">';
    html+='<div class="lrs-anchor-comment-meta">';
    html+='<img class="lrs-anchor-avatar" src="'+esc(root.avatar||'')+'" alt="">';
    html+='<div class="lrs-anchor-meta-copy"><div class="lrs-anchor-author">'+esc(root.author||'Anon')+'</div><div class="lrs-anchor-time">'+esc(root.time||'')+'</div></div>';
    html+='</div>';
    html+=commentMenuHtml(root);
    html+='</div>';
    html+='<div class="lrs-anchor-text">'+(root.content||'')+'</div>';
    html+='<div class="lrs-anchor-actions">'+likeButtonHtml(root)+'<button type="button" class="lrs-anchor-link" data-reply="'+root.id+'" data-group="'+group.group+'">'+esc(cfg.strings.replyHere)+'</button></div>';
    html+=inlineComposerIfNeeded(root.id);
    if(replies.length){
      html+='<div class="lrs-anchor-replies">';
      replies.forEach(function(comment){
        html+='<div class="lrs-anchor-reply">';
        html+='<div class="lrs-anchor-comment-head">';
        html+='<div class="lrs-anchor-comment-meta">';
          html+='<img class="lrs-anchor-avatar" src="'+esc(comment.avatar||'')+'" alt="">';
          html+='<div class="lrs-anchor-meta-copy"><div class="lrs-anchor-author">'+esc(comment.author||'Anon')+'</div><div class="lrs-anchor-time">'+esc(comment.time||'')+'</div></div>';
        html+='</div>';
        html+=commentMenuHtml(comment);
        html+='</div>';
        html+='<div class="lrs-anchor-text">'+(comment.content||'')+'</div>';
        html+='<div class="lrs-anchor-actions">'+likeButtonHtml(comment)+'<button type="button" class="lrs-anchor-link" data-reply="'+comment.id+'" data-group="'+group.group+'">'+esc(cfg.strings.replyHere)+'</button></div>';
        html+=inlineComposerIfNeeded(comment.id);
        html+='</div>';
      });
      html+='</div>';
    }
    html+='</article>';
  }
  if((group.comments||[]).length>3&&!expanded){
    html+='<button type="button" class="lrs-anchor-more" data-expand="'+group.group+'">'+esc(cfg.strings.readMore)+'</button>';
  }
  html+='</div>';
  return html;
}

function groupPreviewText(group){
  var first=(group && group.comments && group.comments.length) ? group.comments[0] : null;
  if(!first){ return ''; }
  var raw=String(first.content_raw||'');
  var labels=[];
  if(/\[gif\]/i.test(raw) || /\.gif(\?|$)/i.test(raw)){ labels.push('GIF'); }
  if(/\[img\]/i.test(raw) || /\.(webp|png|jpe?g|avif)(\?|$)/i.test(raw)){ labels.push('Imagen'); }
  var text=raw
    .replace(/\[gif\][\s\S]*?\[\/gif\]/ig, labels.indexOf('GIF')>=0 ? '[GIF]' : ' ')
    .replace(/\[img\][\s\S]*?\[\/img\]/ig, labels.indexOf('Imagen')>=0 ? '[Imagen]' : ' ')
    .replace(/\[url=[^\]]+\]([\s\S]*?)\[\/url\]/ig, '$1')
    .replace(/\[(?:b|i|spoiler)\]([\s\S]*?)\[\/(?:b|i|spoiler)\]/ig, '$1')
    .replace(/file:\/\/\/\S+/ig, '')
    .replace(/https?:\/\/\S+/ig, '')
    .replace(/\s+/g,' ')
    .trim();
  if(!text && labels.length){
    text='['+labels.join(' + ')+']';
  }
  if(text.length>72){ text=text.slice(0,69)+'...'; }
  return text;
}

function groupListHtml(){
  if(!groups.length){ return ''; }
  var html='<div class="lrs-anchor-group-list">';
  groups.forEach(function(group){
    var first=(group.comments&&group.comments.length)?group.comments[0]:null;
    var preview=groupPreviewText(group);
    var pageLabel='Pag. '+String(Number(group.image_index||0)+1);
    html+='<button type="button" class="lrs-anchor-group-item'+(activeGroupId===group.group?' is-active':'')+'" data-open-group="'+group.group+'">';
    html+='<span class="lrs-anchor-group-item-main">';
    html+='<span class="lrs-anchor-group-item-author">'+esc(first&&first.author?first.author:'Anon')+'</span>';
    html+='<span class="lrs-anchor-group-item-page">'+esc(pageLabel)+'</span>';
    html+='<span class="lrs-anchor-group-item-preview">'+esc(preview||'Abrir hilo')+'</span>';
    html+='</span>';
    html+='<span class="lrs-anchor-group-item-count">'+esc(String(group.count||0))+'</span>';
    html+='</button>';
  });
  html+='</div>';
  return html;
}

function activeGroupSummaryHtml(){
  var group=(activeGroupId && groupMap[activeGroupId]) ? groupMap[activeGroupId] : (groups[0]||null);
  if(!group){ return ''; }
  var first=(group.comments&&group.comments.length)?group.comments[0]:null;
  var preview=groupPreviewText(group);
  var pageLabel='Pag. '+String(Number(group.image_index||0)+1);
  var html='<div class="lrs-anchor-group-picker'+(desktopGroupMenuOpen?' is-open':'')+'">';
  html+='<button type="button" class="lrs-anchor-group-toggle">';
  html+='<span class="lrs-anchor-group-toggle-main">';
  html+='<span class="lrs-anchor-group-item-page">'+esc(pageLabel)+'</span>';
  html+='<span class="lrs-anchor-group-toggle-preview">'+esc(preview || (first&&first.author?first.author:'Seleccionar hilo'))+'</span>';
  html+='</span>';
  html+='<span class="lrs-anchor-group-toggle-meta">'+esc(String(group.count||0))+'</span>';
  html+='<span class="lrs-anchor-group-toggle-caret" aria-hidden="true">▾</span>';
  html+='</button>';
  if(desktopGroupMenuOpen){
    html+='<div class="lrs-anchor-group-dropdown">'+groupListHtml()+'</div>';
  }
  html+='</div>';
  return html;
}

function defaultNewComposerForGroup(group){
  if(!group){ return null; }
  return {
    mode:'new',
    image_index:group.image_index,
    x_pct:group.x_pct,
    y_pct:group.y_pct,
    image_key:group.image_key||'',
    note:cfg.strings.newCommentTitle,
    hideInstructions:true,
    draft:''
  };
}

function composerHtml(target){
  if(!target){ return ''; }
  if(!cfg.isLoggedIn){
    return '<div class="lrs-anchor-composer"><div class="lrs-anchor-note">'+esc(cfg.strings.loginRequired)+'</div><a class="lrs-anchor-login" href="'+esc(cfg.loginUrl)+'">'+esc(cfg.strings.loginButton)+'</a></div>';
  }
  var draft=esc(target.draft||'');
  return ''+
    '<div class="lrs-anchor-composer">'+
      '<div class="lrs-anchor-note">'+esc(target.note||cfg.strings.newCommentTitle)+'</div>'+
      '<textarea id="lrs-anchor-compose-text" placeholder="Escribe tu comentario...">'+draft+'</textarea>'+
      '<div class="lrs-anchor-compose-toolbar">'+
        '<button type="button" class="lrs-anchor-tool" data-compose-action="bold">'+esc(cfg.strings.toolbarBold||'B')+'</button>'+
        '<button type="button" class="lrs-anchor-tool" data-compose-action="italic">'+esc(cfg.strings.toolbarItalic||'I')+'</button>'+
        '<button type="button" class="lrs-anchor-tool" data-compose-action="link">'+esc(cfg.strings.toolbarLink||'Link')+'</button>'+
        '<button type="button" class="lrs-anchor-tool" data-compose-action="spoiler">'+esc(cfg.strings.toolbarSpoiler||'Spoiler')+'</button>'+
        '<button type="button" class="lrs-anchor-tool" data-compose-action="emoji">'+esc(cfg.strings.toolbarEmoji||'Emoji')+'</button>'+
        '<button type="button" class="lrs-anchor-tool" data-compose-action="image">'+esc(cfg.strings.toolbarImage||'Img')+'</button>'+
        '<button type="button" class="lrs-anchor-tool" data-compose-action="gif">'+esc(cfg.strings.toolbarGif||'GIF')+'</button>'+
      '</div>'+
      '<div class="lrs-anchor-composer-actions">'+
        '<button type="button" class="lrs-anchor-submit">'+esc(cfg.strings.publish)+'</button>'+
        '<button type="button" class="lrs-anchor-cancel">'+esc(cfg.strings.cancel)+'</button>'+
      '</div>'+
    '</div>';
}

function placeholderComposerHtml(){
  return ''+
    '<div class="lrs-anchor-composer lrs-anchor-composer--placeholder">'+
      '<div class="lrs-anchor-note">'+esc(cfg.strings.newCommentTitle)+'</div>'+
      '<textarea placeholder="Selecciona un punto para comentar..." disabled></textarea>'+
    '</div>';
}

function choiceHtml(choice){
  if(!choice){ return ''; }
  return '<div class="lrs-anchor-choice">'+
    '<div class="lrs-anchor-note">'+esc(cfg.strings.chooseAction || 'Hay comentarios muy cerca de este punto. Quieres acoplarlo a ese hilo o dejarlo aparte?')+'</div>'+
    '<button type="button" data-choice="attach-nearby">'+esc(cfg.strings.attachNearby || 'Acoplar a este hilo')+'</button>'+
    '<button type="button" data-choice="new-thread">'+esc(cfg.strings.newThreadHere || 'Crear comentario aparte')+'</button>'+
  '</div>';
}

function activeSurfaceBody(){
  var group=activeGroupId && groupMap[activeGroupId] ? groupMap[activeGroupId] : null;
  var isMobile=window.innerWidth<=768;
  var topComposer=null;
  if(composeState && composeState.mode==='new'){
    topComposer=composeState;
  }else if(group && !composeState){
    topComposer=defaultNewComposerForGroup(group);
  }
  var html='';
  if(composeState&&composeState.flash){
    html+='<div class="lrs-anchor-flash">'+esc(composeState.flash)+'</div>';
  }
  if(isMobile){
    if(!(composeState&&composeState.hideInstructions)){
      html+='<div class="lrs-anchor-mobile-copy">';
      html+='<div class="lrs-anchor-note">'+esc(cfg.strings.emptyHintMobile)+'</div>';
      html+='<div class="lrs-anchor-note">'+esc(cfg.strings.scrollHint)+'</div>';
      html+='</div>';
    }
    if(composeState&&composeState.choice){
      html+=choiceHtml(composeState.choice);
    }
    if(topComposer){
      html+=composerHtml(topComposer);
    }else if(composeState && (composeState.mode==='reply' && !composeState.inline)){
      html+=composerHtml(composeState);
    }else if(!group){
      html+=placeholderComposerHtml();
    }else if(!composeState){
      html+=composerHtml(defaultNewComposerForGroup(group));
    }else{
      html+='';
    }
    if(group){
      html+=threadHtml(group);
    }
    return html;
  }
  if(composeState&&composeState.choice){
    html+=choiceHtml(composeState.choice);
  }
  if(groups.length>1){
    html+=activeGroupSummaryHtml();
  }
  if(topComposer){
    html+=composerHtml(topComposer);
  }else if(composeState && (composeState.mode==='reply' && !composeState.inline)){
    html+=composerHtml(composeState);
  }
  html+=threadHtml(group);
  if(!group&&!composeState){
    html+='<div class="lrs-anchor-note" style="margin-top:12px">'+esc(cfg.strings.scrollHint)+'</div>';
  }
  return html;
}

function renderActiveSurface(){
  ensureRail();
  ensureSheet();
  var activeCount=(activeGroupId&&groupMap[activeGroupId]) ? groupMap[activeGroupId].count : groups.reduce(function(sum, group){
    return sum + Number(group.count||0);
  }, 0);
  $('#lrs-anchor-rail .lrs-anchor-group-count, #lrs-anchor-sheet .lrs-anchor-group-count').text(activeCount||0);
  var bodyHtml=activeSurfaceBody();
  if(railReady && state==='comments'){
    $('#lrs-anchor-rail .lrs-anchor-rail-body').html(bodyHtml);
    $('#lrs-anchor-sheet .lrs-anchor-rail-body').empty();
    closeSheet();
  }else if(!railReady && state==='comments'){
    $('#lrs-anchor-sheet .lrs-anchor-rail-body').html(bodyHtml);
    $('#lrs-anchor-rail .lrs-anchor-rail-body').empty();
    openSheet();
  }else{
    $('#lrs-anchor-rail .lrs-anchor-rail-body, #lrs-anchor-sheet .lrs-anchor-rail-body').empty();
    closeSheet();
  }
  $('.lrs-anchor-badge').removeClass('is-active');
  if(activeGroupId){
    $('.lrs-anchor-badge[data-group="'+activeGroupId+'"]').addClass('is-active');
  }
  syncAllLikeButtons();
}

function visibleSurfaceBody(){
  var $body=$('#lrs-anchor-rail .lrs-anchor-rail-body:visible').first();
  if($body.length){ return $body; }
  return $('#lrs-anchor-sheet .lrs-anchor-rail-body:visible').first();
}

function scrollComposerIntoView(){
  setTimeout(function(){
    var $body=visibleSurfaceBody();
    if(!$body.length){ return; }
    var $composer=$body.find('.lrs-anchor-inline-composer:visible #lrs-anchor-compose-text, .lrs-anchor-composer:visible #lrs-anchor-compose-text').first();
    if(!$composer.length){ return; }
    var $target=$composer.closest('.lrs-anchor-inline-composer, .lrs-anchor-composer');
    if(!$target.length){ $target=$composer; }
    var targetTop=Math.max(0, $body.scrollTop() + $target.position().top - 12);
    $body.stop(true).animate({scrollTop:targetTop},180);
  }, 40);
}

function refreshLowerComments(){
  return;
}

function primeImagesThrough(index){
  readerImages().each(function(){
    var $img=$(this);
    if(imageIndexFor($img)>index){ return false; }
    $img.attr('loading','eager');
    if(!$img.attr('fetchpriority') || $img.attr('fetchpriority')==='low'){
      $img.attr('fetchpriority','high');
    }
  });
}

function scrollToGroup(groupId, behavior, attempt){
  var group=groupMap[groupId];
  if(!group){ return; }
  var $img=findImageForGroup(group);
  if(!$img.length){ return; }
  var $reader=readerArea();
  if(!$reader.length){ return; }
  var tries=attempt||0;
  primeImagesThrough(Number(group.image_index||0));
  var position=badgePositionForImage($img,group);
  if(!position){
    if(tries>=8){ return; }
    var el=$img[0];
    el.scrollIntoView({block:'start', behavior:'auto'});
    setTimeout(function(){ scrollToGroup(groupId, behavior, tries+1); }, 220);
    return;
  }
  var readerRect=$reader[0].getBoundingClientRect();
  var absoluteTop=window.pageYOffset + readerRect.top + position.top;
  var targetTop=Math.max(0, absoluteTop - Math.round(window.innerHeight*0.22));
  window.scrollTo({
    top:targetTop,
    behavior:behavior||'smooth'
  });
  if((!$img[0].complete || !$img[0].naturalHeight || $img[0].getBoundingClientRect().height<20) && tries<8){
    setTimeout(function(){ scrollToGroup(groupId, 'auto', tries+1); }, 260);
  }
}

function startNewComposer(anchor){
  activeGroupId=null;
  composeState={
    mode:'new',
    image_index:anchor.image_index,
    x_pct:anchor.x_pct,
    y_pct:anchor.y_pct,
    image_key:anchor.image_key,
    note:cfg.strings.newCommentTitle,
    hideInstructions:!!anchor.hideInstructions
  };
  if(state!=='comments'){
    setState('comments');
  }else{
    renderActiveSurface();
  }
  scrollComposerIntoView();
}

function startGroupComposer(groupId){
  var group=groupMap[groupId];
  if(!group){ return; }
  activeGroupId=groupId;
  composeState={
    mode:'new',
    image_index:group.image_index,
    x_pct:group.x_pct,
    y_pct:group.y_pct,
    image_key:group.image_key||'',
    note:cfg.strings.newCommentTitle,
    hideInstructions:true
  };
  if(window.innerWidth<=768){
    setSheetExpanded(true);
  }else if(!railReady){
    openSheet();
  }
  renderActiveSurface();
  scrollComposerIntoView();
}

function startReplyComposer(groupId,parentId){
  activeGroupId=groupId;
  composeState={
    mode:'reply',
    anchor_group:groupId,
    parent_id:parentId||0,
    note:cfg.strings.replyHere,
    inline:true
  };
  if(!railReady){ openSheet(); }
  renderActiveSurface();
  scrollComposerIntoView();
}

function clearComposer(){
  composeState=null;
  renderActiveSurface();
}

function ensureMobileComposerForGroup(groupId){
  if(window.innerWidth>768){ return; }
  if(!groupId || !groupMap[groupId]){ return; }
  if(composeState && composeState.mode==='new' && activeGroupId===groupId){ return; }
  startGroupComposer(groupId);
}

function postAnchoredComment(){
  if(!composeState){ return; }
  if(saveRequest){ return; }
  var $textarea=$('#lrs-anchor-sheet.is-open #lrs-anchor-compose-text, #lrs-anchor-rail #lrs-anchor-compose-text').filter(':visible').first();
  if(!$textarea.length){
    $textarea=$('#lrs-anchor-compose-text:visible').first();
  }
  var content=$.trim($textarea.val()||'');
  if(!content){ $textarea.focus(); return; }
  var payload={
    action:'bloom_reader_anchor_save',
    nonce:cfg.saveNonce||cfg.nonce,
    post_id:cfg.postId,
    content:content,
    mode:composeState.mode||'new'
  };
  if(composeState.mode==='reply'){
    payload.anchor_group=composeState.anchor_group;
    payload.parent_id=composeState.parent_id||0;
  }else{
    payload.image_index=composeState.image_index;
    payload.x_pct=composeState.x_pct;
    payload.y_pct=composeState.y_pct;
    payload.image_key=composeState.image_key||'';
  }
  $('.lrs-anchor-submit').prop('disabled',true).text('Publicando...');
  saveRequest=$.ajax({
    url:cfg.ajaxUrl,
    method:'POST',
    data:payload,
    timeout:15000
  }).done(function(res){
    if(!res||!res.success){
      composeState.flash=(res&&res.data&&res.data.message)?res.data.message:cfg.strings.genericError;
      renderActiveSurface();
      return;
    }
    if(res.data&&res.data.save_nonce){ cfg.saveNonce=res.data.save_nonce; }
    groups=(res.data.groups&&res.data.groups.groups)?res.data.groups.groups:[];
    groupMap={};
    groups.forEach(function(group){ groupMap[group.group]=group; });
    composeState={flash:(res.data.message||'Comentario publicado.')};
    activeGroupId=res.data.anchor_group||null;
    updateCommentButton();
    renderBadges();
    updateRailLayout();
    renderActiveSurface();
    window.setTimeout(function(){
      if(composeState&&composeState.flash){ composeState=null; renderActiveSurface(); }
    },2200);
  }).fail(function(xhr){
    var message=cfg.strings.genericError;
    if(xhr && xhr.responseJSON && xhr.responseJSON.data){
      if(xhr.responseJSON.data.save_nonce){ cfg.saveNonce=xhr.responseJSON.data.save_nonce; }
      if(xhr.responseJSON.data.message){ message=xhr.responseJSON.data.message; }
    }else if(xhr && xhr.responseText==='-1'){
      message='Tu sesion de comentarios expiro. Recarga la pagina e intenta de nuevo.';
    }
    composeState.flash=message;
    renderActiveSurface();
  }).always(function(){
    saveRequest=null;
  });
}

function reportAnchoredComment(commentId){
  if(!commentId || saveRequest){ return; }
  saveRequest=$.ajax({
    url:cfg.ajaxUrl,
    method:'POST',
    data:{
      action:'bloom_reader_anchor_report',
      nonce:cfg.saveNonce||cfg.nonce,
      comment_id:commentId
    },
    timeout:15000
  }).done(function(res){
    if(!res||!res.success){
      composeState=composeState||{};
      composeState.flash=(res&&res.data&&res.data.message)?res.data.message:cfg.strings.genericError;
      renderActiveSurface();
      return;
    }
    if(res.data&&res.data.save_nonce){ cfg.saveNonce=res.data.save_nonce; }
    groups=(res.data.groups&&res.data.groups.groups)?res.data.groups.groups:groups;
    groupMap={};
    groups.forEach(function(group){ groupMap[group.group]=group; });
    composeState=composeState||{};
    composeState.flash=(res.data.message||cfg.strings.reportedMessage||'Comentario reportado.');
    updateCommentButton();
    renderBadges();
    updateRailLayout();
    renderActiveSurface();
    window.setTimeout(function(){
      if(composeState&&composeState.flash){ composeState.flash=''; renderActiveSurface(); }
    },1800);
  }).fail(function(xhr){
    var message=cfg.strings.genericError;
    if(xhr && xhr.responseJSON && xhr.responseJSON.data){
      if(xhr.responseJSON.data.save_nonce){ cfg.saveNonce=xhr.responseJSON.data.save_nonce; }
      if(xhr.responseJSON.data.message){ message=xhr.responseJSON.data.message; }
    }
    composeState=composeState||{};
    composeState.flash=message;
    renderActiveSurface();
  }).always(function(){
    saveRequest=null;
  });
}

function removeLowerComment(commentId){
  var $comment=$('#comment-'+commentId);
  if(!$comment.length){ return; }
  var $children=$comment.closest('ol.children');
  $comment.remove();
  if($children.length && !$children.children('li.comment').length){
    $children.remove();
  }
  styleLowerComments();
}

function deleteAnchoredComment(commentId){
  if(!commentId || saveRequest){ return; }
  if(!window.confirm(cfg.strings.deleteConfirm||'Este comentario se eliminara de forma permanente. Continuar?')){
    return;
  }
  saveRequest=$.ajax({
    url:cfg.ajaxUrl,
    method:'POST',
    data:{
      action:'bloom_reader_anchor_delete',
      nonce:cfg.saveNonce||cfg.nonce,
      comment_id:commentId
    },
    timeout:15000
  }).done(function(res){
    if(!res || !res.success || !res.data){
      composeState=composeState||{};
      composeState.flash=(res && res.data && res.data.message) || cfg.strings.genericError;
      renderActiveSurface();
      return;
    }
    if(res.data.save_nonce){
      cfg.saveNonce=res.data.save_nonce;
    }
    groups=(res.data.groups && res.data.groups.groups) ? res.data.groups.groups : [];
    groupMap={};
    groups.forEach(function(group){ groupMap[group.group]=group; });
    if(activeGroupId && !groupMap[activeGroupId]){
      activeGroupId=null;
    }
    composeState=composeState||{};
    composeState.flash=res.data.message || 'Comentario eliminado.';
    updateCommentButton();
    renderBadges();
    updateRailLayout();
    renderActiveSurface();
    removeLowerComment(commentId);
  }).fail(function(xhr){
    composeState=composeState||{};
    composeState.flash=(xhr.responseJSON && xhr.responseJSON.data && xhr.responseJSON.data.message) || cfg.strings.genericError;
    renderActiveSurface();
  }).always(function(){
    saveRequest=null;
  });
}

function findCommentById(commentId){
  var found=null;
  groups.some(function(group){
    return (group.comments||[]).some(function(comment){
      if(Number(comment.id)!==Number(commentId)){ return false; }
      found=comment;
      return true;
    });
  });
  return found;
}

function copyTextValue(text){
  var value=String(text||'');
  if(!value){ return; }
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(value).catch(function(){});
    return;
  }
  var el=document.createElement('textarea');
  el.value=value;
  el.setAttribute('readonly','readonly');
  el.style.position='fixed';
  el.style.top='-9999px';
  document.body.appendChild(el);
  el.select();
  try{ document.execCommand('copy'); }catch(err){}
  document.body.removeChild(el);
}

function anchorPayloadFromImage($img, clientX, clientY){
  var coords=percentCoords($img, clientX, clientY);
  if(!coords){ return null; }
  return {
    image_index:imageIndexFor($img),
    x_pct:coords.x,
    y_pct:coords.y,
    image_key:imageKeyFor($img)
  };
}

function handleAnchorIntent(target, clientX, clientY){
  if(!hasCommentMode()){ return; }
  var $img=$(target).closest('img.ts-main-image');
  if(!$img.length){ return; }
  var anchor=anchorPayloadFromImage($img, clientX, clientY);
  if(!anchor){ return; }
  var nearby=findNearbyGroup(anchor.image_index, anchor.x_pct, anchor.y_pct);
  if(nearby){
    activeGroupId=nearby.group;
    composeState={
      choice:{
        anchor:anchor,
        nearby_group:nearby.group
      },
      note:cfg.strings.chooseAction || 'Hay comentarios muy cerca de este punto. Quieres acoplarlo a ese hilo o dejarlo aparte?',
      hideInstructions:true
    };
    if(state!=='comments'){
      setState('comments');
    }else{
      renderActiveSurface();
    }
    scrollToGroup(nearby.group,'smooth');
    return;
  }
  anchor.hideInstructions=true;
  startNewComposer(anchor);
}

function handleDesktopImageClick(e){
  if(!hasCommentMode()){ return; }
  if(isUiTarget(e.target)){ return; }
  var target=resolveReaderImage(e.target, e.clientX, e.clientY);
  if(!target){ return; }
  e.preventDefault();
  e.stopPropagation();
  e.stopImmediatePropagation();
  if(e.shiftKey){
    handleAnchorIntent(target, e.clientX, e.clientY);
    return;
  }
  if(desktopClickCounter.timer){
    clearTimeout(desktopClickCounter.timer);
  }
  if(desktopClickCounter.target===target){
    desktopClickCounter.count+=1;
  }else{
    desktopClickCounter.target=target;
    desktopClickCounter.count=1;
  }
  desktopClickCounter.lastX=e.clientX;
  desktopClickCounter.lastY=e.clientY;
  desktopClickCounter.timer=setTimeout(function(){
    desktopClickCounter.count=0;
    desktopClickCounter.target=null;
  },420);
  if(desktopClickCounter.count>=3){
    handleAnchorIntent(target, desktopClickCounter.lastX, desktopClickCounter.lastY);
    desktopClickCounter.count=0;
    desktopClickCounter.target=null;
  }
}

function handleTouchStart(e){
  if(!hasCommentMode()){ return; }
  if(isUiTarget(e.target)){ return; }
  var touch=e.touches&&e.touches[0];
  if(!touch){ return; }
  mobileTapCounter.startX=touch.clientX;
  mobileTapCounter.startY=touch.clientY;
  mobileTapCounter.sourceTarget=e.target;
}

function handleTouchEnd(e){
  if(!hasCommentMode()){ return; }
  if(isUiTarget(e.target)){ return; }
  var touch=e.changedTouches&&e.changedTouches[0];
  if(!touch){ return; }
  var target=resolveReaderImage(mobileTapCounter.sourceTarget, touch.clientX, touch.clientY);
  if(!target){ return; }
  var dx=touch.clientX-(mobileTapCounter.startX||0);
  var dy=touch.clientY-(mobileTapCounter.startY||0);
  var dist=Math.sqrt(dx*dx+dy*dy);
  if(dist>10){
    mobileTapCounter.count=0;
    mobileTapCounter.target=null;
    mobileTapCounter.sourceTarget=null;
    return;
  }
  if(mobileTapCounter.timer){
    clearTimeout(mobileTapCounter.timer);
  }
  if(mobileTapCounter.target===target){
    mobileTapCounter.count+=1;
  }else{
    mobileTapCounter.target=target;
    mobileTapCounter.count=1;
  }
  mobileTapCounter.lastX=touch.clientX;
  mobileTapCounter.lastY=touch.clientY;
  mobileTapCounter.timer=setTimeout(function(){
    mobileTapCounter.count=0;
    mobileTapCounter.target=null;
    mobileTapCounter.sourceTarget=null;
  },650);
  if(mobileTapCounter.count>=3){
    e.preventDefault();
    e.stopPropagation();
    handleAnchorIntent(target, mobileTapCounter.lastX, mobileTapCounter.lastY);
    mobileTapCounter.count=0;
    mobileTapCounter.target=null;
    mobileTapCounter.sourceTarget=null;
  }
}

function setScrollActive(){
  document.body.classList.add('lrs-anchor-scroll-active');
  if(scrollBadgeTimer){ clearTimeout(scrollBadgeTimer); }
  scrollBadgeTimer=setTimeout(function(){
    document.body.classList.remove('lrs-anchor-scroll-active');
  },620);
}

function installReaderObserver(){
  var reader=document.getElementById('readerarea');
  if(!reader||readerObserver){ return; }
  readerObserver=new MutationObserver(function(mutations){
    var relevant=mutations.some(function(mutation){
      var nodes=[].slice.call(mutation.addedNodes||[]).concat([].slice.call(mutation.removedNodes||[]));
      return nodes.some(function(node){
        if(!node || node.nodeType!==1){ return false; }
        if(node.matches && node.matches('img.ts-main-image')){ return true; }
        return !!(node.querySelector && node.querySelector('img.ts-main-image'));
      });
    });
    if(!relevant){ return; }
    prepareReaderImages();
    renderBadges();
    updateRailLayout();
  });
  readerObserver.observe(reader,{childList:true,subtree:true});
}

function lowerCommentId($comment){
  var raw=String($comment.attr('id')||'');
  var match=raw.match(/comment-(\d+)/);
  return match ? match[1] : '';
}

function lowerCommentAuthor($comment){
  return $.trim($comment.find('> .comment-body .comment-author .fn').first().text()||'');
}

function lowerCommentText($comment){
  var parts=[];
  $comment.find('> .comment-body > p').each(function(){
    var $p=$(this);
    if($p.find('.lrs-anchor-jump, .lrs-anchor-report, .lrs-anchor-like').length){ return; }
    var text=$.trim($p.text()||'');
    if(text){ parts.push(text); }
  });
  return parts.join('\n').trim();
}

function updateLikeButtons(commentId, liked, count){
  var $buttons=$('.lrs-anchor-like[data-comment-id="'+commentId+'"]');
  $buttons.each(function(){
    var $button=$(this);
    $button.attr('data-liked', liked ? '1' : '0');
    $button.toggleClass('is-liked', !!liked);
    $button.find('.lrs-anchor-like-count').text(String(Number(count||0)));
    $button.find('.lrs-anchor-like-label').text(liked ? (cfg.strings.liked||'Te gusta') : (cfg.strings.like||'Me gusta'));
  });
}

function syncAllLikeButtons(){
  groups.forEach(function(group){
    (group.comments||[]).forEach(function(comment){
      updateLikeButtons(comment.id, !!comment.liked, Number(comment.like_count||0));
    });
  });
}

function toggleLikeComment(commentId){
  if(!commentId || saveRequest){ return; }
  if(!cfg.isLoggedIn){
    window.location.href=cfg.loginUrl;
    return;
  }
  saveRequest=$.ajax({
    url:cfg.ajaxUrl,
    method:'POST',
    data:{
      action:'bloom_reader_anchor_like',
      nonce:cfg.saveNonce||cfg.nonce,
      comment_id:commentId
    },
    timeout:15000
  }).done(function(res){
    if(!res || !res.success || !res.data){
      composeState=composeState||{};
      composeState.flash=(res && res.data && res.data.message) || cfg.strings.genericError;
      renderActiveSurface();
      return;
    }
    if(res.data.save_nonce){ cfg.saveNonce=res.data.save_nonce; }
    groups=(res.data.groups&&res.data.groups.groups)?res.data.groups.groups:groups;
    groupMap={};
    groups.forEach(function(group){ groupMap[group.group]=group; });
    updateCommentButton();
    renderBadges();
    updateRailLayout();
    updateLikeButtons(commentId, !!res.data.liked, Number(res.data.like_count||0));
    styleLowerComments();
    renderActiveSurface();
  }).fail(function(xhr){
    var message=cfg.strings.genericError;
    if(xhr && xhr.responseJSON && xhr.responseJSON.data){
      if(xhr.responseJSON.data.save_nonce){ cfg.saveNonce=xhr.responseJSON.data.save_nonce; }
      if(xhr.responseJSON.data.message){ message=xhr.responseJSON.data.message; }
    }
    composeState=composeState||{};
    composeState.flash=message || cfg.strings.likeLogin || cfg.strings.genericError;
    renderActiveSurface();
  }).always(function(){
    saveRequest=null;
  });
}

function lowerCommentMenuHtml(commentId, canReport){
  var items='';
  if(cfg.canModerate){
    items+='<button type="button" class="lrs-bottom-comment-menu-action" data-menu-action="moderate" data-comment-id="'+commentId+'">'+esc(cfg.strings.moderateComment||'Moderar comentario')+'</button>';
  }
  if(cfg.isLoggedIn){
    items+='<button type="button" class="lrs-bottom-comment-menu-action" data-menu-action="delete-comment" data-comment-id="'+commentId+'">'+esc(cfg.strings.deleteComment||'Eliminar comentario')+'</button>';
  }
  items+='<button type="button" class="lrs-bottom-comment-menu-action" data-menu-action="copy-comment" data-comment-id="'+commentId+'">'+esc(cfg.strings.copyComment||'Copiar comentario')+'</button>';
  items+='<button type="button" class="lrs-bottom-comment-menu-action" data-menu-action="copy-user-name" data-comment-id="'+commentId+'">'+esc(cfg.strings.copyUserName||'Copiar nombre de usuario')+'</button>';
  items+='<button type="button" class="lrs-bottom-comment-menu-action" data-menu-action="copy-comment-id" data-comment-id="'+commentId+'">'+esc(cfg.strings.copyCommentId||'Copiar ID de comentario')+'</button>';
  if(canReport){
    items+='<button type="button" class="lrs-bottom-comment-menu-action" data-menu-action="report" data-comment-id="'+commentId+'">'+esc(cfg.strings.report||'Reportar')+'</button>';
  }
  return '<div class="lrs-anchor-comment-menu lrs-bottom-comment-menu'+(String(lowerCommentMenuOpen)===String(commentId)?' is-open':'')+'">'+
    '<button type="button" class="lrs-bottom-comment-menu-toggle" data-comment-id="'+commentId+'" aria-label="Mas opciones">⋮</button>'+
    '<div class="lrs-anchor-comment-menu-panel lrs-bottom-comment-menu-panel">'+items+'</div>'+
  '</div>';
}

function lowerToolbarHtml(){
  return '<div class="lrs-bottom-compose-toolbar-wrap"><div class="lrs-anchor-compose-toolbar lrs-bottom-compose-toolbar">'+
    '<button type="button" class="lrs-bottom-tool" data-compose-action="bold">'+esc(cfg.strings.toolbarBold||'B')+'</button>'+
    '<button type="button" class="lrs-bottom-tool" data-compose-action="italic">'+esc(cfg.strings.toolbarItalic||'I')+'</button>'+
    '<button type="button" class="lrs-bottom-tool" data-compose-action="link">'+esc(cfg.strings.toolbarLink||'Link')+'</button>'+
    '<button type="button" class="lrs-bottom-tool" data-compose-action="spoiler">'+esc(cfg.strings.toolbarSpoiler||'Spoiler')+'</button>'+
    '<button type="button" class="lrs-bottom-tool" data-compose-action="emoji">'+esc(cfg.strings.toolbarEmoji||'Emoji')+'</button>'+
    '<button type="button" class="lrs-bottom-tool" data-compose-action="image">'+esc(cfg.strings.toolbarImage||'Img')+'</button>'+
    '<button type="button" class="lrs-bottom-tool" data-compose-action="gif">'+esc(cfg.strings.toolbarGif||'GIF')+'</button>'+
  '</div></div>';
}

function styleLowerComments(){
  var $comments=$('#comments.comments-area');
  if(!$comments.length){ return; }
  $comments.addClass('lrs-comments');
  var totalCount=$comments.find('li.comment').length;
  $comments.find('.releases h2 span').attr('data-count', totalCount>0 ? String(totalCount) : '0');
  var $respond=$comments.find('#respond, .comment-respond').first();
  var $list=$comments.find('ol.comment-list').first();
  if($respond.length && $list.length && !$respond.closest('li.comment').length && !$respond.prev().is($comments.find('.releases').first())){
    $respond.insertBefore($list);
  }
  var $textarea=$comments.find('#comment').first();
  if($textarea.length && !$comments.find('.lrs-bottom-compose-toolbar-wrap').length){
    $textarea.after(lowerToolbarHtml());
  }
  $comments.find('li.comment').each(function(){
    var $comment=$(this);
    var commentId=lowerCommentId($comment);
    if(!commentId){ return; }
    var $body=$comment.children('.comment-body');
    if(!$body.length){ return; }
    var $menus=$body.children('.lrs-bottom-comment-menu').add($body.children('.lrs-bottom-comment-head').children('.lrs-bottom-comment-menu'));
    if(!$menus.length){
      var canReport=$body.find('.lrs-anchor-report').length>0;
      $body.prepend(lowerCommentMenuHtml(commentId, canReport));
      $menus=$body.children('.lrs-bottom-comment-menu');
    }else if($menus.length>1){
      $menus.not($menus.first()).remove();
      $menus=$menus.first();
    }
    if(!$body.children('.lrs-bottom-comment-head').length){
      var $menu=$menus.first();
      var $author=$body.children('.comment-author').first();
      var $meta=$body.children('.comment-meta, .commentmetadata').first();
      if($author.length){
        var $head=$('<div class="lrs-bottom-comment-head"></div>');
        var $metaWrap=$('<div class="lrs-bottom-comment-author-meta"></div>');
        $metaWrap.append($author);
        if($meta.length){
          $metaWrap.append($meta);
        }
        $head.append($metaWrap);
        if($menu.length){
          $head.append($menu);
        }
        $body.prepend($head);
      }
    }else{
      var $headExisting=$body.children('.lrs-bottom-comment-head').first();
      var $menuExisting=$menus.first();
      if($menuExisting.length && !$headExisting.children('.lrs-bottom-comment-menu').length){
        $headExisting.append($menuExisting);
      }
      $body.children('.lrs-bottom-comment-menu').not($headExisting.children('.lrs-bottom-comment-menu')).remove();
    }
    var $actions=$body.children('.lrs-bottom-comment-actions').first();
    if(!$actions.length){
      $actions=$('<div class="lrs-bottom-comment-actions"></div>').appendTo($body);
    }
    [
      $body.children('.lrs-anchor-jump-wrap').first(),
      $body.children('.lrs-anchor-like-wrap').first(),
      $body.children('.reply').first()
    ].forEach(function($part){
      if($part && $part.length && !$part.parent().is($actions)){
        $actions.append($part);
      }
    });
    if(!$actions.children().length){
      $actions.remove();
    }
    $body.find('.reply a').each(function(){
      var $link=$(this);
      if($link.attr('data-lrsReplyReady')){ return; }
      $link.attr('data-lrsReplyReady','1');
      $link.removeAttr('onclick');
      $link.attr('href','#');
    });
  });
}

function moveLowerReplyForm($link){
  if(!$link || !$link.length){ return; }
  var commentId=$link.attr('data-commentid') || $link.data('commentid') || 0;
  var postId=$link.attr('data-postid') || $link.data('postid') || cfg.postId;
  var belowElement=$link.attr('data-belowelement') || $link.data('belowelement') || ('comment-' + commentId);
  var respondId=$link.attr('data-respondelement') || $link.data('respondelement') || 'respond';
  if(window.addComment && typeof window.addComment.moveForm==='function'){
    window.addComment.moveForm(String(belowElement), String(commentId), String(respondId), String(postId));
  }
  window.setTimeout(function(){
    var $respond=$('#'+respondId);
    if(!$respond.length){ $respond=$('#respond, .comment-respond').first(); }
    if($respond.length){
      var top=Math.max(0, $respond.offset().top - 120);
      $('html,body').stop(true).animate({scrollTop:top},220);
      var $textarea=$respond.find('#comment, textarea').first();
      if($textarea.length){ $textarea.trigger('focus'); }
    }
  }, 60);
}

function bindReaderSurfaceEvents(){
  var reader=readerArea()[0];
  if(!reader || readerSurfaceEventsBound){ return; }
  document.addEventListener('click',handleDesktopImageClick,true);
  reader.addEventListener('touchstart',handleTouchStart,{passive:true,capture:true});
  reader.addEventListener('touchend',handleTouchEnd,{passive:false,capture:true});
  readerSurfaceEventsBound=true;
}

function installEditableSafeZone(){
  if(editableShieldInstalled){ return; }
  editableShieldInstalled=true;
  [
    'mousedown',
    'mouseup',
    'selectstart',
    'copy',
    'cut',
    'paste',
    'contextmenu',
    'dragstart',
    'keydown',
    'touchstart',
    'touchend',
    'pointerdown',
    'pointerup'
  ].forEach(function(type){
    window.addEventListener(type,function(e){
      if(!isEditableZoneTarget(e.target)){ return; }
      e.stopPropagation();
      if(typeof e.stopImmediatePropagation==='function'){
        e.stopImmediatePropagation();
      }
    },true);
  });
}

function bindGlobalEvents(){
  $(document).on('input change keyup', '#lrs-anchor-compose-text', function(){
    syncComposeDraftFromField(this);
  });
  $(document).on('click','.lrs-anchor-badge',function(e){
    e.preventDefault();
    e.stopPropagation();
    activeGroupId=$(this).attr('data-group');
    if(window.innerWidth<=768){
      ensureMobileComposerForGroup(activeGroupId);
      setState('comments');
      renderActiveSurface();
    }else{
      setState('comments');
      startGroupComposer(activeGroupId);
    }
    window.setTimeout(function(){
      var $body=visibleSurfaceBody();
      if($body.length){ $body.scrollTop(0); }
    },40);
  });
  $(document).on('click','.lrs-anchor-font-btn',function(e){
    e.preventDefault();
    var direction=Number($(this).attr('data-font-scale')||0);
    if(!direction){ return; }
      storeFontScale(fontScale + (direction>0 ? 0.22 : -0.22));
    applyFontScale();
  });
  $(document).on('click','.lrs-anchor-more',function(){
    expandedGroups[$(this).attr('data-expand')]=true;
    renderActiveSurface();
  });
  $(document).on('click','.lrs-anchor-group-item',function(){
    activeGroupId=$(this).attr('data-open-group');
    desktopGroupMenuOpen=false;
    composeState=null;
    ensureMobileComposerForGroup(activeGroupId);
    setState('comments');
    scrollToGroup(activeGroupId,'smooth');
    renderActiveSurface();
    window.setTimeout(function(){
      var $body=visibleSurfaceBody();
      if($body.length){ $body.scrollTop(0); }
    },40);
  });
  $(document).on('click','.lrs-anchor-group-toggle',function(e){
    e.preventDefault();
    e.stopPropagation();
    stashComposeDraft();
    desktopGroupMenuOpen=!desktopGroupMenuOpen;
    renderActiveSurface();
  });
  $(document).on('click',function(e){
    if(openCommentMenuId && !$(e.target).closest('.lrs-anchor-comment-menu').length){
      stashComposeDraft();
      openCommentMenuId=null;
      renderActiveSurface();
      return;
    }
    if(lowerCommentMenuOpen && !$(e.target).closest('.lrs-bottom-comment-menu').length){
      lowerCommentMenuOpen=null;
      $('.lrs-bottom-comment-menu').removeClass('is-open');
    }
    if(!desktopGroupMenuOpen){ return; }
    if($(e.target).closest('.lrs-anchor-group-picker').length){ return; }
    stashComposeDraft();
    desktopGroupMenuOpen=false;
    renderActiveSurface();
  });
  $(document).on('click','.lrs-anchor-jump',function(e){
    e.preventDefault();
    var groupId=$(this).attr('data-group');
    if(!groupId){ return; }
    activeGroupId=groupId;
    composeState=null;
    setState('comments');
    scrollToGroup(groupId,'smooth');
    renderActiveSurface();
  });
  $(document).on('click','.lrs-anchor-link[data-reply], .lrs-anchor-link[data-reply-group]',function(){
    var $btn=$(this);
    var groupId=$btn.attr('data-group')||$btn.attr('data-reply-group');
    var parentId=$btn.attr('data-reply')||0;
    startReplyComposer(groupId,parentId);
  });
  $(document).on('click','#comments.comments-area .reply a',function(e){
    e.preventDefault();
    e.stopPropagation();
    if(typeof e.stopImmediatePropagation==='function'){
      e.stopImmediatePropagation();
    }
    moveLowerReplyForm($(this));
    return false;
  });
  $(document).on('click','.lrs-anchor-like',function(e){
    e.preventDefault();
    e.stopPropagation();
    var commentId=$(this).attr('data-comment-id');
    if(!commentId){ return; }
    toggleLikeComment(commentId);
  });
  $(document).on('click','.lrs-anchor-tool',function(e){
    e.preventDefault();
    var action=$(this).attr('data-compose-action');
    if(action==='bold'){ insertTextAroundSelection('[b]','[/b]','texto'); return; }
    if(action==='italic'){ insertTextAroundSelection('[i]','[/i]','texto'); return; }
    if(action==='spoiler'){ insertTextAroundSelection('[spoiler]','[/spoiler]','spoiler'); return; }
    if(action==='emoji'){ insertPlainTextAtCursor(' :) '); return; }
    if(action==='image'){ uploadCommentMedia('image','anchor'); return; }
    if(action==='gif'){ uploadCommentMedia('gif','anchor'); return; }
    if(action==='link'){
      var url=window.prompt(cfg.strings.promptLink||'Pega la URL:');
      if(!url){ return; }
      insertTextAroundSelection('[url='+url+']','[/url]','enlace');
    }
  });
  $(document).on('click','.lrs-bottom-tool',function(e){
    e.preventDefault();
    var action=$(this).attr('data-compose-action');
    if(action==='bold'){ insertLowerTextAroundSelection('[b]','[/b]','texto'); return; }
    if(action==='italic'){ insertLowerTextAroundSelection('[i]','[/i]','texto'); return; }
    if(action==='spoiler'){ insertLowerTextAroundSelection('[spoiler]','[/spoiler]','spoiler'); return; }
    if(action==='emoji'){ insertLowerPlainTextAtCursor(' :) '); return; }
    if(action==='image'){ uploadCommentMedia('image','lower'); return; }
    if(action==='gif'){ uploadCommentMedia('gif','lower'); return; }
    if(action==='link'){
      var url=window.prompt(cfg.strings.promptLink||'Pega la URL:');
      if(!url){ return; }
      insertLowerTextAroundSelection('[url='+url+']','[/url]','enlace');
    }
  });
  $(document).on('click','.lrs-anchor-comment-menu-toggle',function(e){
    e.preventDefault();
    e.stopPropagation();
    stashComposeDraft();
    var commentId=$(this).attr('data-comment-id');
    openCommentMenuId=(Number(openCommentMenuId)===Number(commentId)) ? null : commentId;
    renderActiveSurface();
  });
  $(document).on('click','.lrs-anchor-comment-menu-action',function(e){
    e.preventDefault();
    e.stopPropagation();
    var action=$(this).attr('data-menu-action');
    var commentId=$(this).attr('data-comment-id');
    var comment=findCommentById(commentId);
    openCommentMenuId=null;
    if(action==='report'){ reportAnchoredComment(commentId); return; }
    if(action==='copy-comment' && comment){ copyTextValue(comment.content_raw||''); return; }
    if(action==='copy-user-name' && comment){ copyTextValue(comment.author||''); return; }
    if(action==='copy-comment-id'){ copyTextValue(commentId); return; }
    if(action==='copy-user-id' && comment){ copyTextValue(comment.author_user_id||''); return; }
    if(action==='delete-comment'){ deleteAnchoredComment(commentId); return; }
    if(action==='moderate' && cfg.commentAdminBase){
      window.open(cfg.commentAdminBase + commentId, '_blank', 'noopener');
    }
  });
  $(document).on('click','.lrs-bottom-comment-menu-toggle',function(e){
    e.preventDefault();
    e.stopPropagation();
    var commentId=$(this).attr('data-comment-id');
    lowerCommentMenuOpen=(String(lowerCommentMenuOpen)===String(commentId)) ? null : commentId;
    $('.lrs-bottom-comment-menu').removeClass('is-open');
    if(lowerCommentMenuOpen){
      $('.lrs-bottom-comment-menu-toggle[data-comment-id="'+lowerCommentMenuOpen+'"]').closest('.lrs-bottom-comment-menu').addClass('is-open');
    }
  });
  $(document).on('click','.lrs-bottom-comment-menu-action',function(e){
    e.preventDefault();
    e.stopPropagation();
    var $action=$(this);
    var action=$action.attr('data-menu-action');
    var commentId=$action.attr('data-comment-id');
    var $comment=$action.closest('li.comment');
    lowerCommentMenuOpen=null;
    $('.lrs-bottom-comment-menu').removeClass('is-open');
    if(action==='report'){
      var $reportButton=$comment.find('.lrs-anchor-report[data-comment-id="'+commentId+'"]').first();
      if($reportButton.length){
        $reportButton.trigger('click');
      }
      return;
    }
    if(action==='copy-comment'){
      copyTextValue(lowerCommentText($comment));
      return;
    }
    if(action==='copy-user-name'){
      copyTextValue(lowerCommentAuthor($comment));
      return;
    }
    if(action==='copy-comment-id'){
      copyTextValue(commentId);
      return;
    }
    if(action==='delete-comment'){
      deleteAnchoredComment(commentId);
      return;
    }
    if(action==='moderate' && cfg.commentAdminBase){
      window.open(cfg.commentAdminBase + commentId, '_blank', 'noopener');
    }
  });
  $(document).on('click','.lrs-anchor-link[data-report], .lrs-anchor-report',function(e){
    e.preventDefault();
    var commentId=$(this).attr('data-report')||$(this).attr('data-comment-id');
    if(!commentId){ return; }
    reportAnchoredComment(commentId);
  });
  $(document).on('click','.lrs-anchor-media-toggle',function(e){
    e.preventDefault();
    var $button=$(this);
    var targetId=$button.attr('data-target');
    var $block=$button.closest('.lrs-anchor-media-block');
    var $view=$block.children('.lrs-anchor-media-view').first();
    if((!$view.length) && targetId){
      $view=$('#'+targetId);
    }
    if(!$view.length){ return; }
    var willOpen=$view.attr('hidden')!==undefined;
    if(willOpen){
      $view.removeAttr('hidden');
      $view.find('img').each(function(){
        var img=this;
        var src=img.dataset.src || '';
        var $img=$(img);
        var $fallback=$img.siblings('.lrs-anchor-media-fallback');
        if(!$img.attr('data-bound')){
          $img.on('error',function(){
            $img.hide();
            if($fallback.length){
              $fallback.removeAttr('hidden');
            }
          });
          $img.on('load',function(){
            $img.show();
            if($fallback.length){
              $fallback.attr('hidden','hidden');
            }
          });
          $img.attr('data-bound','1');
        }
        if(!img.getAttribute('src') && src){
          if(($view.attr('data-kind')||'')==='gif'){
            img.setAttribute('loading','eager');
          }
          img.setAttribute('src', src);
        }
      });
      $button.text($button.attr('data-close-label')||cfg.strings.hideImage||'Ocultar imagen');
    }else{
      $view.attr('hidden','hidden');
      $button.text($button.attr('data-open-label')||cfg.strings.viewImage||'Ver imagen');
    }
  });
  $(document).on('click','[data-choice="attach-nearby"]',function(){
    if(!composeState||!composeState.choice){ return; }
    startGroupComposer(composeState.choice.nearby_group);
  });
  $(document).on('click','[data-choice="new-thread"]',function(){
    if(!composeState||!composeState.choice){ return; }
    startNewComposer(composeState.choice.anchor);
  });
  $(document).on('click','.lrs-anchor-submit',postAnchoredComment);
  $(document).on('click','.lrs-anchor-cancel',function(){
    clearComposer();
  });
  window.addEventListener('scroll',setScrollActive,{passive:true});
  window.addEventListener('resize',function(){
    var focused=document.activeElement;
    var typingMobile=window.innerWidth<=768 && focused && focused.id==='lrs-anchor-compose-text';
    if(typingMobile){ return; }
    stashComposeDraft();
    renderBadges();
    updateRailLayout();
    renderActiveSurface();
  });
}

function boot(){
  if(booted){ return; }
  if(!$('#lrs-navbar').length||!readerImages().length){ return; }
  booted=true;
  applyFontScale();
  ensureCommentsButton();
  ensureRail();
  ensureSheet();
  bindRailResizeObserver();
  installEditableSafeZone();
  prepareReaderImages();
  bindReaderSurfaceEvents();
  installReaderObserver();
  bindGlobalEvents();
  styleLowerComments();
  fetchGroups(function(){
    updateRailLayout();
    renderActiveSurface();
  });
  setState(state);
}

var bootTimer=setInterval(function(){
  if(booted){
    clearInterval(bootTimer);
    return;
  }
  boot();
},180);

$(boot);

})(jQuery);
