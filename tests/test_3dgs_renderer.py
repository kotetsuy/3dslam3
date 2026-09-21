"""Analytical tests of visibility, empty pixels and differentiable compositing."""
import unittest
import numpy as np
import torch
from optimize_3dgs import TileRenderer


class RendererTests(unittest.TestCase):
    def renderer(self, xyz):
        # Two spheres project exactly onto the first pixel center.
        prediction = {
            'images': np.zeros((1,8,8,3),np.uint8),
            'intrinsics': np.array([[[1,0,.5],[0,1,.5],[0,0,1]]],np.float32),
            'extrinsics': np.array([np.eye(4)[:3]],np.float32),
        }
        return TileRenderer(np.array(xyz,np.float32),np.full(len(xyz),.1,np.float32),
                            prediction,np.ones((1,8,8),np.float32),'cpu')

    def test_depth_sorted_over_white(self):
        renderer = self.renderer([[0,0,2],[0,0,1]])  # deliberately far first
        rgb = torch.tensor([[0.,0.,1.],[1.,0.,0.]])
        result,alpha = renderer.render([0],rgb,torch.zeros(2),torch.zeros(2))
        # Red .5 over blue .5 over white: .5*red + .25*blue + .25*white.
        torch.testing.assert_close(result[0,0],torch.tensor([.75,.25,.5]))
        self.assertAlmostEqual(float(alpha[0,0]),.75)

    def test_behind_camera_has_no_effect(self):
        renderer = self.renderer([[0,0,-1]])
        result,alpha = renderer.render([0],torch.zeros((1,3)),torch.zeros(1),torch.zeros(1))
        torch.testing.assert_close(result,torch.ones_like(result))
        torch.testing.assert_close(alpha,torch.zeros_like(alpha))

    def test_scale_opacity_gradients_match_finite_difference(self):
        renderer = self.renderer([[0,0,1]])
        rgb = torch.tensor([[.2,.3,.4]])
        opacity = torch.tensor([.3],requires_grad=True)
        size = torch.tensor([.1],requires_grad=True)
        def value():
            return renderer.render([0],rgb,opacity,size)[0][0,1].sum()
        value().backward()
        for parameter in [opacity,size]:
            analytic = float(parameter.grad[0])
            with torch.no_grad():
                parameter[0] += .001
                plus = float(value())
                parameter[0] -= .002
                minus = float(value())
                parameter[0] += .001
            self.assertAlmostEqual(analytic,(plus-minus)/.002,delta=.0003)


if __name__ == '__main__':
    unittest.main()
