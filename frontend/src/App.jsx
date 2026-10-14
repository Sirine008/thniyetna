import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import ProtectedRoute from './components/ProtectedRoute';
import Citizen from './pages/Citizen';
import CitizenMap from './pages/CitizenMap';
import Claims from './pages/Claims';
import Driver from './pages/Driver';
import DriverAlerts from './pages/DriverAlerts';
import DriverMap from './pages/DriverMap';
import Home from './pages/Home';
import Login from './pages/Login';
import Ministry from './pages/Ministry';
import Report from './pages/Report';
import './styles/app.css';

const guard = (roles, element) => <ProtectedRoute roles={roles}>{element}</ProtectedRoute>;

export default function App() {
  return <BrowserRouter><Routes>
    <Route path="/" element={<Home/>}/>
    <Route path="/login" element={<Login/>}/>
    <Route path="/citizen" element={guard(['citizen'], <Citizen/>)}/>
    <Route path="/citizen/map" element={guard(['citizen'], <CitizenMap/>)}/>
    <Route path="/citizen/report" element={guard(['citizen'], <Report/>)}/>
    <Route path="/citizen/claims" element={guard(['citizen'], <Claims/>)}/>
    <Route path="/driver" element={guard(['bus_driver'], <Driver/>)}/>
    <Route path="/driver/map" element={guard(['bus_driver'], <DriverMap/>)}/>
    <Route path="/driver/alerts" element={guard(['bus_driver'], <DriverAlerts/>)}/>
    <Route path="/ministry/equipment" element={guard(['equipment_supervisor'], <Ministry ministry="equipment"/>)}/>
    <Route path="/ministry/transport" element={guard(['transport_supervisor'], <Ministry ministry="transport"/>)}/>
    <Route path="*" element={<Navigate to="/" replace/>}/>
  </Routes></BrowserRouter>;
}
