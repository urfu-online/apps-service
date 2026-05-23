// Service Detail Modal Component
import React from 'react';

interface ServiceDetailProps {
  service: any;
  onClose: () => void;
}

export const ServiceDetail: React.FC<ServiceDetailProps> = ({ service, onClose }) => {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h3 className="text-lg font-medium text-gray-900">Service Details: {service.display_name || service.name}</h3>
          <button 
            onClick={onClose}
            className="text-gray-400 hover:text-gray-500 focus:outline-none"
          >
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        <div className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            <div>
              <h4 className="text-md font-medium text-gray-900 mb-2">Basic Information</h4>
              <div className="bg-gray-50 p-4 rounded">
                <p className="text-sm"><span className="font-medium">Name:</span> {service.name}</p>
                <p className="text-sm"><span className="font-medium">Display Name:</span> {service.display_name || '-'}</p>
                <p className="text-sm"><span className="font-medium">Version:</span> {service.version || '-'}</p>
                <p className="text-sm"><span className="font-medium">Visibility:</span> {service.visibility}</p>
                <p className="text-sm"><span className="font-medium">Status:</span> 
                  <span className={`ml-2 px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                    ${service.status === 'running' ? 'bg-green-100 text-green-800' : 
                      service.status === 'stopped' ? 'bg-red-100 text-red-800' : 
                      'bg-yellow-100 text-yellow-800'}`}>
                    {service.status === 'running' ? 'Running' : 
                     service.status === 'stopped' ? 'Stopped' : 'Partial'}
                  </span>
                </p>
              </div>
            </div>
            
            <div>
              <h4 className="text-md font-medium text-gray-900 mb-2">Routing Information</h4>
              <div className="bg-gray-50 p-4 rounded">
                {service.routing && service.routing.length > 0 ? (
                  service.routing.map((route: any, index: number) => (
                    <div key={index} className="mb-3">
                      <p className="text-sm"><span className="font-medium">Type:</span> {route.type}</p>
                      {route.type === 'domain' && (
                        <p className="text-sm"><span className="font-medium">Domain:</span> {route.domain}</p>
                      )}
                      {route.type === 'port' && (
                        <p className="text-sm"><span className="font-medium">Port:</span> {route.port}</p>
                      )}
                      {route.type === 'subfolder' && (
                        <p className="text-sm"><span className="font-medium">Base Domain:</span> {route.base_domain}</p>
                      )}
                      {route.type === 'subfolder' && (
                        <p className="text-sm"><span className="font-medium">Path:</span> {route.path}</p>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-gray-500">No routing information</p>
                )}
              </div>
            </div>
          </div>
          
          <div className="mb-6">
            <h4 className="text-md font-medium text-gray-900 mb-2">Service Configuration</h4>
            <div className="bg-gray-50 p-4 rounded font-mono text-sm">
              <pre>{JSON.stringify(service, null, 2)}</pre>
            </div>
          </div>
          
          <div className="flex justify-end space-x-3">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-500 text-white rounded-md hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-gray-500"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};