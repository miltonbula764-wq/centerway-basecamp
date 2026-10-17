// Applied only to the CI test process and its Node workers, never to install/build.
const blocked = () => { throw new Error('Frontend tests must mock network requests; outbound access is disabled.'); };
globalThis.fetch = blocked;
for (const protocol of ['http', 'https']) {
  const mod = require('node:' + protocol);
  mod.request = blocked;
  mod.get = blocked;
}
// Vite can use local sockets; reject Internet targets, including backend endpoints.
const net = require('node:net');
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  const options = args[0];
  const host = options && typeof options === 'object' ? options.host : args[1];
  if (typeof host === 'string' && !['localhost', '127.0.0.1', '::1'].includes(host)) blocked();
  return connect.apply(this, args);
};
