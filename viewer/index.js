fetch('/api/sets').then(r => {if (!r.ok) throw Error(r.status); return r.json();}).then(data => {
  const list = document.getElementById('sets');
  for (const s of data.sets) {
    const li = document.createElement('li'), a = document.createElement('a');
    a.href = '/viewer?set=' + encodeURIComponent(s.id); a.textContent = s.name;
    li.append(a, document.createElement('br'), `${s.num_gaussians.toLocaleString()} Gaussian / ${(s.bytes/1e6).toFixed(1)} MB`);
    list.append(li);
  }
  if (!data.sets.length) document.getElementById('error').textContent = '表示できる3DGSがまだありません。';
}).catch(e => document.getElementById('error').textContent = '一覧を取得できませんでした: ' + e.message);
