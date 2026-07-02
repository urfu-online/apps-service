// Layout components
import React from 'react';
import { useLocation } from 'react-router-dom';

export const Header: React.FC = () => {
  return (
    <header className="bg-white shadow">
      <div className="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8 flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900">Platform Manager</h1>
        <div className="flex items-center space-x-4">
          <button className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
            Refresh
          </button>
        </div>
      </div>
    </header>
  );
};

export const Sidebar: React.FC = () => {
  const location = useLocation();
  
  const isActive = (path: string) => {
    return location.pathname === path;
  };

  return (
    <aside className="w-64 bg-gray-800 text-white min-h-screen">
      <div className="p-4">
        <h2 className="text-xl font-bold mb-4">Navigation</h2>
        <nav className="space-y-2">
          <a 
            href="/" 
            className={`block px-4 py-2 rounded ${isActive('/') ? 'bg-blue-600' : 'hover:bg-gray-700'}`}
          >
            Dashboard
          </a>
          <a 
            href="/services" 
            className={`block px-4 py-2 rounded ${isActive('/services') ? 'bg-blue-600' : 'hover:bg-gray-700'}`}
          >
            Services
          </a>
          <a 
            href="/logs" 
            className={`block px-4 py-2 rounded ${isActive('/logs') ? 'bg-blue-600' : 'hover:bg-gray-700'}`}
          >
            Logs
          </a>
          <a 
            href="/backups" 
            className={`block px-4 py-2 rounded ${isActive('/backups') ? 'bg-blue-600' : 'hover:bg-gray-700'}`}
          >
            Backups
          </a>
        </nav>
      </div>
    </aside>
  );
};

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="flex min-h-screen bg-gray-100">
      <Sidebar />
      <main className="flex-1">
        <Header />
        <div className="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </div>
      </main>
    </div>
  );
};